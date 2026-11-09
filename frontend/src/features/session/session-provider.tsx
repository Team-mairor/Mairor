"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { clearFacePhoto } from "@/features/face";
import type { PouchItem } from "@/features/pouch";
import type { VideoItem } from "@/features/video";
import { api, ApiError, setCsrfToken, type LoginResponse, type User } from "@/lib/api";

import {
  createRun,
  EMPTY_RUN,
  invalidateRun as invalidated,
  type RunPatch,
  type RunState,
  type StartRunInput,
} from "./run-state";
import type { ReportSummary } from "./types";
export { EMPTY_RUN, type Choice, type RunState } from "./run-state";

/** 검수 완료 카드에는 실행에 사용할 guideId가 있어야 한다. */
export type PendingGuide = { title: string; ytid: string | null } & (
  { status: "pending"; guideId?: null } | { status: "approved"; guideId: string }
);

export interface SessionState {
  loggedIn: boolean;
  email: string;
  /** 서버의 닉네임. 없으면 "" */
  nickname: string;
  /** 로그아웃하지 않았는데 세션이 끝남. 다음 로그인 전까지 인트로가 만료 안내로 보낸다 */
  sessionExpired: boolean;
  /** 이 기기에서 온보딩을 본 적 있음 */
  onboarded: boolean;
  /** 이 기기에서 튜토리얼 안내를 본 적 있음 */
  tutSeen: boolean;
  pouch: PouchItem[];
  reports: ReportSummary[];
  pendingGuide: PendingGuide | null;
  run: RunState;
}

const EMPTY_STATE: SessionState = {
  loggedIn: false,
  email: "",
  nickname: "",
  sessionExpired: false,
  onboarded: false,
  tutSeen: false,
  pouch: [],
  reports: [],
  pendingGuide: null,
  run: EMPTY_RUN,
};

// 목업 단계·파우치가 바뀌면 판을 올려, 예전 단계 기준으로 저장된 파우치·기록을 버린다
const STORAGE_KEY = "mairor-session-v2";

interface SessionContextValue {
  state: SessionState;
  /** 브라우저에 저장된 값(파우치·리포트)을 state에 넣었다. 저장 데이터를 보여 주는 화면은 이 값을 기다린다 */
  storageLoaded: boolean;
  /** 내 계정 조회가 끝났다(성공·실패·시간 초과). 로그인 분기는 이 값이 true일 때 결정한다 */
  sessionChecked: boolean;
  update: (patch: Partial<SessionState> | ((prev: SessionState) => Partial<SessionState>)) => void;
  /** 로그인 성공·세션 확인. 로그인 상태는 이것과 signOut·expireSession으로만 바꾼다. csrfToken이 없으면(Google 흉내) 토큰은 그대로 */
  signIn: (user: Pick<User, "email" | "nickname">, csrfToken?: string) => void;
  /** 로그아웃. 토큰을 지우고 로그인 이력도 지운다(만료 안내 없음) */
  signOut: () => void;
  /** API가 401을 돌려줘 세션이 끝났다. 실행을 버리고 로그아웃 상태로 바꾸며, 로그인 이력이 있으면 다음 로그인 전까지 만료 안내를 띄운다 */
  expireSession: () => void;
  updateRun: (patch: RunPatch | ((prev: RunState) => RunPatch), expectedRunId?: string) => void;
  bindGuide: (expectedRunId: string, version: number, picked: VideoItem) => void;
  enterTutorial: (expectedRunId: string, photoOk: boolean) => void;
  completeRun: (expectedRunId: string) => void;
  invalidateRun: (expectedRunId: string) => void;
  endRun: (expectedRunId: string) => void;
  isCurrentRun: (expectedRunId: string) => boolean;
  /** 새 실행 시작. 이전 실행의 진행 데이터는 버린다 */
  startRun: (input: StartRunInput) => void;
  reset: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

// 내 계정 조회가 늦으면 저장된 로그인 상태로 시작한다
const ME_TIMEOUT_MS = 5000;

// 실행은 메모리에만 두고 기기 설정·파우치·완료 리포트만 저장한다. 인증은 내 계정 조회로 확인한다.
export function SessionProvider({
  children,
  seed,
}: {
  children: ReactNode;
  /**
   * 저장값이 없는 기기에서 처음 보여 줄 파우치·리포트. API가 붙기 전 샘플을 넣는 자리다 (app/layout.tsx).
   * layout에서 한 번만 넘기므로 처음 값으로 고정한다
   */
  seed?: Pick<SessionState, "pouch" | "reports">;
}) {
  const [initial] = useState<SessionState>(() => ({ ...EMPTY_STATE, ...seed }));
  const [state, setState] = useState<SessionState>(initial);
  const [storageLoaded, setStorageLoaded] = useState(false);
  const [sessionChecked, setSessionChecked] = useState(false);
  const activeRunId = useRef("");
  const previousRunId = useRef("");
  useLayoutEffect(() => {
    if (previousRunId.current !== state.run.id) clearFacePhoto(previousRunId.current);
    previousRunId.current = state.run.id;
    activeRunId.current = state.run.phase === "invalidated" ? "" : state.run.id;
  }, [state.run.id, state.run.phase]);
  const isCurrentRun = useCallback((id: string) => !!id && activeRunId.current === id, []);

  // 같은 계정이 이어질 때만 파우치를 둔다. 아니면 비우고 서버 목록을 기다린다(샘플·다른 계정 목록을 내 제품으로 쓰지 않게)
  const signIn = useCallback<SessionContextValue["signIn"]>((user, csrfToken) => {
    if (csrfToken !== undefined) setCsrfToken(csrfToken);
    setState((prev) => ({
      ...prev,
      run: prev.email && prev.email !== user.email ? EMPTY_RUN : prev.run,
      loggedIn: true,
      email: user.email,
      nickname: user.nickname ?? "",
      sessionExpired: false,
      pouch: prev.loggedIn && prev.email === user.email ? prev.pouch : [],
    }));
  }, []);

  // 로그아웃·만료 때는 이전 계정 목록을 지우고 처음 샘플로 돌린다
  const signOut = useCallback(() => {
    activeRunId.current = "";
    clearFacePhoto();
    setCsrfToken(null);
    setState((prev) => ({
      ...prev,
      run: EMPTY_RUN,
      loggedIn: false,
      email: "",
      nickname: "",
      sessionExpired: false,
      pouch: initial.pouch,
    }));
  }, [initial]);

  const expireSession = useCallback(() => {
    activeRunId.current = "";
    clearFacePhoto();
    setCsrfToken(null);
    setState((prev) => ({
      ...prev,
      run: EMPTY_RUN,
      loggedIn: false,
      email: "",
      nickname: "",
      sessionExpired: prev.loggedIn || prev.sessionExpired,
      pouch: initial.pouch,
    }));
  }, [initial]);

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
      if (saved && typeof saved === "object" && !Array.isArray(saved)) {
        // eslint-disable-next-line react-hooks/set-state-in-effect -- 저장소는 브라우저에서만 읽을 수 있다
        setState({ ...initial, ...saved, run: EMPTY_RUN });
      }
    } catch {
      // 깨진 저장값은 기본값으로 시작한다
    }
    setStorageLoaded(true);

    // 앱을 다시 열면 세션 쿠키로 로그인 상태를 확인하고 CSRF 토큰을 받는다.
    // 401이면 로그아웃 상태로 바꾸고, 서버에 닿지 못하는 등 그 밖의 실패는 저장된 상태를 그대로 쓴다.
    // 저장된 loggedIn이 로그인 이력 플래그다(로그인 성공 때 켜고 로그아웃 때 끈다). 켜진 채 401이면 만료로 본다.
    // AbortSignal.any는 Safari 17.4 미만에 없어 시간 제한도 같은 컨트롤러로 끊는다
    let unmounted = false;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), ME_TIMEOUT_MS);
    api
      .get<LoginResponse>("/v1/users/me", { signal: controller.signal })
      .then(({ user, csrfToken }) => {
        if (!unmounted) signIn(user, csrfToken);
      })
      .catch((e) => {
        if (unmounted) return;
        if (e instanceof ApiError && e.code === "UNAUTHORIZED") expireSession();
      })
      .finally(() => {
        clearTimeout(timer);
        if (!unmounted) setSessionChecked(true);
      });
    return () => {
      unmounted = true;
      clearTimeout(timer);
      controller.abort();
    };
  }, [initial, signIn, expireSession]);

  // storageLoaded는 저장값을 state에 넣은 다음 렌더부터 true라, 기본값으로 저장값을 덮어쓰지 않는다
  useEffect(() => {
    if (!storageLoaded) return;
    try {
      const { run: _run, ...persisted } = state;
      void _run;
      localStorage.setItem(STORAGE_KEY, JSON.stringify(persisted));
    } catch {
      // 저장 실패는 화면에 영향 없음
    }
  }, [storageLoaded, state]);

  const update = useCallback<SessionContextValue["update"]>((patch) => {
    setState((prev) => ({ ...prev, ...(typeof patch === "function" ? patch(prev) : patch) }));
  }, []);

  const updateRun = useCallback<SessionContextValue["updateRun"]>((patch, expectedRunId) => {
    setState((prev) => ({
      ...prev,
      run:
        (expectedRunId !== undefined && prev.run.id !== expectedRunId) ||
        prev.run.phase === "invalidated"
          ? prev.run
          : { ...prev.run, ...(typeof patch === "function" ? patch(prev.run) : patch) },
    }));
  }, []);

  const startRun = useCallback((input: StartRunInput) => {
    clearFacePhoto();
    const run = createRun(input, crypto.randomUUID());
    activeRunId.current = run.id;
    setState((prev) => ({ ...prev, run }));
  }, []);

  const endRun = useCallback((expectedRunId: string) => {
    if (activeRunId.current === expectedRunId) activeRunId.current = "";
    setState((prev) => (prev.run.id !== expectedRunId ? prev : { ...prev, run: EMPTY_RUN }));
    clearFacePhoto(expectedRunId);
  }, []);
  const invalidateRun = useCallback((expectedRunId: string) => {
    if (activeRunId.current === expectedRunId) activeRunId.current = "";
    clearFacePhoto(expectedRunId);
    setState((prev) =>
      prev.run.id !== expectedRunId ? prev : { ...prev, run: invalidated(prev.run) },
    );
  }, []);
  const bindGuide = useCallback((expectedRunId: string, version: number, picked: VideoItem) => {
    setState((prev) => {
      const r = prev.run;
      if (
        r.id !== expectedRunId ||
        r.mode !== "guide" ||
        r.phase === "invalidated" ||
        r.guideVersion === version
      )
        return prev;
      if (r.guideVersion !== null) return { ...prev, run: invalidated(r) };
      return { ...prev, run: { ...r, guideVersion: version, picked } };
    });
  }, []);
  const enterTutorial = useCallback((expectedRunId: string, photoOk: boolean) => {
    setState((prev) =>
      prev.run.id !== expectedRunId || prev.run.phase === "invalidated"
        ? prev
        : { ...prev, run: { ...prev.run, photoOk, captures: [], phase: "tutorial" } },
    );
  }, []);
  const completeRun = useCallback((expectedRunId: string) => {
    setState((prev) =>
      prev.run.id !== expectedRunId || prev.run.phase !== "tutorial"
        ? prev
        : { ...prev, run: { ...prev.run, phase: "completed" } },
    );
  }, []);
  const reset = useCallback(() => {
    activeRunId.current = "";
    clearFacePhoto();
    setState(initial);
  }, [initial]);

  const value = useMemo(
    () => ({
      state,
      storageLoaded,
      sessionChecked,
      update,
      signIn,
      signOut,
      expireSession,
      updateRun,
      startRun,
      isCurrentRun,
      endRun,
      bindGuide,
      enterTutorial,
      completeRun,
      invalidateRun,
      reset,
    }),
    [
      state,
      storageLoaded,
      sessionChecked,
      update,
      signIn,
      signOut,
      expireSession,
      updateRun,
      startRun,
      isCurrentRun,
      endRun,
      bindGuide,
      enterTutorial,
      completeRun,
      invalidateRun,
      reset,
    ],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

/** 화면에서 부르는 이름. 닉네임이 없으면 이메일 앞부분 */
export function displayName({ nickname, email }: Pick<SessionState, "nickname" | "email">) {
  return nickname || email.split("@")[0];
}

export function useSession() {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession은 SessionProvider 안에서만 쓸 수 있습니다");
  return context;
}
