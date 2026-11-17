"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import type { PouchItem } from "@/domain/pouch";
import { api, ApiError, setCsrfToken, type LoginResponse, type User } from "@/lib/api";

import { authStore, EMPTY_AUTH, useAuth, type AuthState } from "./auth";
import { deviceStore, useDevice } from "./device";
import { pendingGuideStore, usePendingGuide, type PendingGuide } from "./pending-guide";
import { pouchStore, useMyPouch } from "./pouch-store";
import { reportStore, useStoredReports } from "./report-store";
import { RunProvider, useRun } from "./run-store";
import type { ReportSummary } from "./types";

export { EMPTY_RUN, type Choice, type RunState } from "./run-state";
export type { PendingGuide } from "./pending-guide";

/** 상태를 한꺼번에 본 모양. 테스트와 개발용 화면이 쓴다. 제품 화면은 상태별 훅을 쓴다 */
export interface SessionState extends AuthState {
  onboarded: boolean;
  tutSeen: boolean;
  pouch: PouchItem[];
  reports: ReportSummary[];
  pendingGuide: PendingGuide | null;
  run: ReturnType<typeof useRun>["run"];
}

interface ActionsValue {
  /** 저장값(로그인·기기·파우치·리포트·검수 대기)을 모두 state에 넣었다. 저장 데이터를 보여 주는 화면은 이 값을 기다린다 */
  storageLoaded: boolean;
  /** 내 계정 조회가 끝났다(성공·실패·시간 초과). 로그인 분기는 이 값이 true일 때 결정한다 */
  sessionChecked: boolean;
  /** 로그인 성공·세션 확인. 로그인 상태는 이것과 signOut·expireSession으로만 바꾼다. csrfToken이 없으면(Google 흉내) 토큰은 그대로 */
  signIn: (user: Pick<User, "email" | "nickname">, csrfToken?: string) => void;
  /** 로그아웃. 토큰을 지우고 로그인 이력도 지운다(만료 안내 없음) */
  signOut: () => void;
  /** API가 401을 돌려줘 세션이 끝났다. 실행을 버리고 로그아웃 상태로 바꾸며, 로그인 이력이 있으면 다음 로그인 전까지 만료 안내를 띄운다 */
  expireSession: () => void;
  /** 모든 상태를 처음 값으로 되돌린다 */
  reset: () => void;
}

const ActionsContext = createContext<ActionsValue | null>(null);

// 내 계정 조회가 늦으면 저장된 로그인 상태로 시작한다
const ME_TIMEOUT_MS = 5000;

/**
 * 로그인·기기 설정·파우치·리포트·검수 대기·실행 저장소를 묶는다.
 * 실행은 메모리에만 두고 나머지는 저장소마다 다른 키로 저장한다. 인증은 내 계정 조회로 확인한다.
 */
export function SessionProvider({
  children,
  seed,
}: {
  children: ReactNode;
  /** 앱 화면에서는 쓰지 않는다. 테스트가 명시적으로 초기 데이터를 넣을 때만 사용한다. */
  seed?: Pick<SessionState, "pouch" | "reports">;
}) {
  return (
    <authStore.Provider>
      <deviceStore.Provider>
        <pouchStore.Provider initial={seed?.pouch}>
          <reportStore.Provider initial={seed?.reports}>
            <pendingGuideStore.Provider>
              <RunProvider>
                <ActionsProvider>{children}</ActionsProvider>
              </RunProvider>
            </pendingGuideStore.Provider>
          </reportStore.Provider>
        </pouchStore.Provider>
      </deviceStore.Provider>
    </authStore.Provider>
  );
}

function ActionsProvider({ children }: { children: ReactNode }) {
  const auth = authStore.useStore();
  const device = deviceStore.useStore();
  const pouch = pouchStore.useStore();
  const reports = reportStore.useStore();
  const pending = pendingGuideStore.useStore();
  const { clearRun } = useRun();
  const [sessionChecked, setSessionChecked] = useState(false);
  const storageLoaded =
    auth.loaded && device.loaded && pouch.loaded && reports.loaded && pending.loaded;

  // 비동기 응답이 와도 지금 로그인 상태로 판단한다
  const current = useRef(auth.value);
  useLayoutEffect(() => {
    current.current = auth.value;
  }, [auth.value]);

  const { set: setAuth } = auth;
  const { set: setDevice } = device;
  const { set: setPouch } = pouch;
  const { set: setReports } = reports;
  const { set: setPending } = pending;

  // 같은 계정이 이어질 때만 파우치·리포트를 둔다. 아니면 비우고 서버 목록을 기다린다(다른 계정 목록을 내 제품으로 쓰지 않게)
  const signIn = useCallback<ActionsValue["signIn"]>(
    (user, csrfToken) => {
      if (csrfToken !== undefined) setCsrfToken(csrfToken);
      const prev = current.current;
      const same = prev.loggedIn && prev.email === user.email;
      if (prev.email && prev.email !== user.email) clearRun();
      const next = {
        loggedIn: true,
        email: user.email,
        nickname: user.nickname ?? "",
        sessionExpired: false,
      };
      // 다시 그리기 전에 들어오는 응답도 바뀐 로그인 상태로 판단하도록 바로 맞춘다
      current.current = next;
      setAuth(next);
      if (!same) {
        setPouch([]);
        setReports([]);
      }
    },
    [clearRun, setAuth, setPouch, setReports],
  );

  // 로그아웃·만료 때는 이전 계정의 데이터를 비운다
  const endSession = useCallback(
    (sessionExpired: boolean) => {
      clearRun();
      setCsrfToken(null);
      const ended = { ...EMPTY_AUTH, sessionExpired };
      current.current = ended;
      setAuth(ended);
      setPouch([]);
      setReports([]);
    },
    [clearRun, setAuth, setPouch, setReports],
  );
  const signOut = useCallback(() => endSession(false), [endSession]);
  const expireSession = useCallback(
    () => endSession(current.current.loggedIn || current.current.sessionExpired),
    [endSession],
  );

  const reset = useCallback(() => {
    clearRun();
    setAuth(EMPTY_AUTH);
    setDevice({ onboarded: false, tutSeen: false });
    setPouch([]);
    setReports([]);
    setPending(null);
  }, [clearRun, setAuth, setDevice, setPouch, setReports, setPending]);

  // 앱을 다시 열면 세션 쿠키로 로그인 상태를 확인하고 CSRF 토큰을 받는다.
  // 401이면 로그아웃 상태로 바꾸고, 서버에 닿지 못하는 등 그 밖의 실패는 저장된 상태를 그대로 쓴다.
  // 저장된 loggedIn이 로그인 이력 플래그다(로그인 성공 때 켜고 로그아웃 때 끈다). 켜진 채 401이면 만료로 본다.
  // AbortSignal.any는 Safari 17.4 미만에 없어 시간 제한도 같은 컨트롤러로 끊는다
  useEffect(() => {
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
  }, [signIn, expireSession]);

  const value = useMemo(
    () => ({ storageLoaded, sessionChecked, signIn, signOut, expireSession, reset }),
    [storageLoaded, sessionChecked, signIn, signOut, expireSession, reset],
  );

  return <ActionsContext.Provider value={value}>{children}</ActionsContext.Provider>;
}

/** 로그인·로그아웃·세션 만료와 저장값·세션 확인 상태 */
export function useSessionActions() {
  const context = useContext(ActionsContext);
  if (!context) throw new Error("useSessionActions는 SessionProvider 안에서만 쓸 수 있습니다");
  return context;
}

/**
 * 여러 상태를 한꺼번에 보는 모양. 테스트와 개발용 화면이 쓴다.
 * 제품 화면은 useAuth · useDevice · useMyPouch · useStoredReports · usePendingGuide · useRun을 필요한 것만 쓴다
 */
export function useSession() {
  const auth = useAuth();
  const device = useDevice();
  const { pouch, setPouch } = useMyPouch();
  const { reports, setReports } = useStoredReports();
  const { pendingGuide, setPendingGuide } = usePendingGuide();
  const { run, replaceRun, ...runActions } = useRun();
  const { set: setAuth } = authStore.useStore();
  const { set: setDevice } = deviceStore.useStore();
  const actions = useSessionActions();
  const state: SessionState = {
    ...auth,
    onboarded: device.onboarded,
    tutSeen: device.tutSeen,
    pouch,
    reports,
    pendingGuide,
    run,
  };
  const latest = useRef(state);
  useLayoutEffect(() => {
    latest.current = state;
  });
  const update = useCallback(
    (patch: Partial<SessionState> | ((prev: SessionState) => Partial<SessionState>)) => {
      const next = typeof patch === "function" ? patch(latest.current) : patch;
      const { loggedIn, email, nickname, sessionExpired } = next;
      if (
        loggedIn !== undefined ||
        email !== undefined ||
        nickname !== undefined ||
        sessionExpired !== undefined
      )
        setAuth((prev) => ({
          loggedIn: loggedIn ?? prev.loggedIn,
          email: email ?? prev.email,
          nickname: nickname ?? prev.nickname,
          sessionExpired: sessionExpired ?? prev.sessionExpired,
        }));
      if (next.run) replaceRun(next.run);
      if (next.pouch) setPouch(next.pouch);
      if (next.reports) setReports(next.reports);
      if ("pendingGuide" in next) setPendingGuide(next.pendingGuide ?? null);
      if (next.onboarded !== undefined || next.tutSeen !== undefined)
        setDevice((prev) => ({
          onboarded: next.onboarded ?? prev.onboarded,
          tutSeen: next.tutSeen ?? prev.tutSeen,
        }));
    },
    [setAuth, setDevice, replaceRun, setPouch, setReports, setPendingGuide],
  );
  return { state, update, ...runActions, ...actions };
}
