"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { PouchItem } from "@/features/pouch";
import type { VideoItem } from "@/features/video";
import { api, ApiError, setCsrfToken, type LoginResponse, type User } from "@/lib/api";

import type { ReportSummary } from "./types";

/** 검수 대기 중인 가이드 (홈 카드) */
export interface PendingGuide {
  title: string;
  ytid: string | null;
  status: "pending" | "approved";
}

/** 레퍼런스 제품 하나에 대한 선택. none: 없이 진행, pouch: 내 파우치 제품 */
export type Choice = { kind: "none" } | { kind: "pouch"; id: string };

/** 한 번의 따라 하기 실행 동안 화면을 건너 이어지는 값 */
export interface RunState {
  /** 실행 id. 완료 기록을 이 id로 한 번만 만든다 (GUIDE-010) */
  id: string;
  picked: VideoItem | null;
  /** 분석 없이 시작한 경로 */
  replay: "guide" | "report" | null;
  /** 이 실행이 요청한 분석 작업. 로딩 화면은 주소의 jobId와 같을 때만 picked를 쓴다 */
  jobId: string | null;
  /** 얼굴 등록 완료 */
  faceReg: boolean;
  /** 레퍼런스 제품 id → 선택. 없으면 기본 매칭(보유 > 추천 대체) */
  choice: Record<string, Choice>;
  /** 추천 대체 제품 켜짐 여부 (기본 켜짐) */
  subOn: Record<string, boolean>;
  /** 단계 사진 저장 동의 */
  photoOk: boolean;
  /** 사진을 저장한 단계 번호 */
  captures: number[];
}

export interface SessionState {
  loggedIn: boolean;
  email: string;
  /** 서버의 닉네임. 없으면 "" */
  nickname: string;
  /** 로그아웃하지 않았는데 세션이 끝남. 다음 로그인 전까지 인트로가 만료 안내로 보낸다 (API-USERS-004) */
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

export const EMPTY_RUN: RunState = {
  id: "",
  picked: null,
  replay: null,
  jobId: null,
  faceReg: false,
  choice: {},
  subOn: {},
  photoOk: false,
  captures: [],
};

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
  /** 브라우저에 저장된 값(파우치·리포트·실행)을 state에 넣었다. 저장 데이터를 보여 주는 화면은 이 값을 기다린다 */
  storageLoaded: boolean;
  /** 내 계정 조회가 끝났다(성공·실패·시간 초과). 로그인 분기는 이 값이 true일 때 결정한다 */
  sessionChecked: boolean;
  update: (patch: Partial<SessionState> | ((prev: SessionState) => Partial<SessionState>)) => void;
  /** 로그인 성공·세션 확인. 로그인 상태는 이것과 signOut으로만 바꾼다. csrfToken이 없으면(Google 흉내) 토큰은 그대로 */
  signIn: (user: Pick<User, "email" | "nickname">, csrfToken?: string) => void;
  /** 로그아웃. 토큰을 지우고 로그인 이력도 지운다(만료 안내 없음) */
  signOut: () => void;
  updateRun: (patch: Partial<RunState> | ((prev: RunState) => Partial<RunState>)) => void;
  /** 새 실행 시작. 이전 실행의 진행 데이터는 버린다 (GUIDE-011) */
  startRun: (run: Partial<RunState>) => void;
  reset: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

// 내 계정 조회가 늦으면 저장된 로그인 상태로 시작한다
const ME_TIMEOUT_MS = 5000;

// ponytail: 브라우저 저장소 하나에 통째로 저장. loggedIn·email만 서버 세션(내 계정 조회) 기준으로 맞춘다.
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

  const signIn = useCallback<SessionContextValue["signIn"]>((user, csrfToken) => {
    if (csrfToken !== undefined) setCsrfToken(csrfToken);
    setState((prev) => ({
      ...prev,
      loggedIn: true,
      email: user.email,
      nickname: user.nickname ?? "",
      sessionExpired: false,
    }));
  }, []);

  const signOut = useCallback(() => {
    setCsrfToken(null);
    setState((prev) => ({
      ...prev,
      loggedIn: false,
      email: "",
      nickname: "",
      sessionExpired: false,
    }));
  }, []);

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
      if (saved && typeof saved === "object") {
        // eslint-disable-next-line react-hooks/set-state-in-effect -- 저장소는 브라우저에서만 읽을 수 있다
        setState({ ...initial, ...saved, run: { ...EMPTY_RUN, ...saved.run } });
      }
    } catch {
      // 깨진 저장값은 기본값으로 시작한다
    }
    setStorageLoaded(true);

    // 앱을 다시 열면 세션 쿠키로 로그인 상태를 확인하고 CSRF 토큰을 받는다 (USERS-004).
    // 401이면 로그아웃 상태로 바꾸고, 서버에 닿지 못하는 등 그 밖의 실패는 저장된 상태를 그대로 쓴다.
    // 저장된 loggedIn이 로그인 이력 플래그다(로그인 성공 때 켜고 로그아웃 때 끈다). 켜진 채 401이면 만료로 본다.
    // AbortSignal.any는 Safari 17.4 미만에 없어 시간 제한도 같은 컨트롤러로 끊는다
    let unmounted = false;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), ME_TIMEOUT_MS);
    api
      .get<LoginResponse>("/v1/users/me", { signal: controller.signal })
      .then(({ user, csrfToken }) => signIn(user, csrfToken))
      .catch((e) => {
        if (e instanceof ApiError && e.code === "UNAUTHORIZED") {
          setState((prev) => ({
            ...prev,
            loggedIn: false,
            email: "",
            nickname: "",
            sessionExpired: prev.loggedIn || prev.sessionExpired,
          }));
        }
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
  }, [initial, signIn]);

  // storageLoaded는 저장값을 state에 넣은 다음 렌더부터 true라, 기본값으로 저장값을 덮어쓰지 않는다
  useEffect(() => {
    if (!storageLoaded) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      // 저장 실패는 화면에 영향 없음
    }
  }, [storageLoaded, state]);

  const update = useCallback<SessionContextValue["update"]>((patch) => {
    setState((prev) => ({ ...prev, ...(typeof patch === "function" ? patch(prev) : patch) }));
  }, []);

  const updateRun = useCallback<SessionContextValue["updateRun"]>((patch) => {
    setState((prev) => ({
      ...prev,
      run: { ...prev.run, ...(typeof patch === "function" ? patch(prev.run) : patch) },
    }));
  }, []);

  const startRun = useCallback((run: Partial<RunState>) => {
    setState((prev) => ({ ...prev, run: { ...EMPTY_RUN, id: `run${Date.now()}`, ...run } }));
  }, []);

  const reset = useCallback(() => setState(initial), [initial]);

  const value = useMemo(
    () => ({
      state,
      storageLoaded,
      sessionChecked,
      update,
      signIn,
      signOut,
      updateRun,
      startRun,
      reset,
    }),
    [state, storageLoaded, sessionChecked, update, signIn, signOut, updateRun, startRun, reset],
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
