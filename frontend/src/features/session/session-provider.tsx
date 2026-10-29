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

import {
  DEFAULT_POUCH,
  DEFAULT_REPORTS,
  type PouchItem,
  type ReportSummary,
  type VideoItem,
} from "@/lib/mock-data";

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
  faceReg: false,
  choice: {},
  subOn: {},
  photoOk: false,
  captures: [],
};

const DEFAULT_STATE: SessionState = {
  loggedIn: false,
  email: "",
  onboarded: false,
  tutSeen: false,
  pouch: DEFAULT_POUCH,
  reports: DEFAULT_REPORTS,
  pendingGuide: null,
  run: EMPTY_RUN,
};

const STORAGE_KEY = "mairor-session";

interface SessionContextValue {
  state: SessionState;
  /** 저장된 값을 읽기 전에는 false. 로그인 분기는 이 값이 true일 때 결정한다 */
  hydrated: boolean;
  update: (patch: Partial<SessionState> | ((prev: SessionState) => Partial<SessionState>)) => void;
  updateRun: (patch: Partial<RunState> | ((prev: RunState) => Partial<RunState>)) => void;
  /** 새 실행 시작. 이전 실행의 진행 데이터는 버린다 (GUIDE-011) */
  startRun: (run: Partial<RunState>) => void;
  reset: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

// ponytail: 브라우저 저장소 하나에 통째로 저장. 서버 세션·토큰이 붙으면 loggedIn·email만 서버 기준으로 바꾼다.
export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SessionState>(DEFAULT_STATE);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
      if (saved && typeof saved === "object") {
        // eslint-disable-next-line react-hooks/set-state-in-effect -- 저장소는 브라우저에서만 읽을 수 있다
        setState({ ...DEFAULT_STATE, ...saved, run: { ...EMPTY_RUN, ...saved.run } });
      }
    } catch {
      // 깨진 저장값은 기본값으로 시작한다
    }
    setHydrated(true);
  }, []);

  // hydrated는 저장값을 state에 넣은 다음 렌더부터 true라, 기본값으로 저장값을 덮어쓰지 않는다
  useEffect(() => {
    if (!hydrated) return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      // 저장 실패는 화면에 영향 없음
    }
  }, [hydrated, state]);

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

  const reset = useCallback(() => setState(DEFAULT_STATE), []);

  const value = useMemo(
    () => ({ state, hydrated, update, updateRun, startRun, reset }),
    [state, hydrated, update, updateRun, startRun, reset],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession은 SessionProvider 안에서만 쓸 수 있습니다");
  return context;
}
