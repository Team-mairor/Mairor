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

import { clearRegisteredGaugeBaseline } from "@/domain/gauge";
import type { VideoItem } from "@/domain/video";
import { clearFacePhoto } from "@/vision/face";

import {
  createRun,
  continueAnalysisRun,
  EMPTY_RUN,
  invalidateRun as invalidated,
  type RunPatch,
  type RunState,
  type StartRunInput,
} from "./run-state";
import { discardUnsavedStepPhotos, resetStepPhotos } from "./step-photos";

interface RunValue {
  run: RunState;
  updateRun: (patch: RunPatch | ((prev: RunState) => RunPatch), expectedRunId?: string) => void;
  bindGuide: (expectedRunId: string, version: number, picked: VideoItem) => void;
  enterTutorial: (expectedRunId: string, photoOk: boolean) => void;
  completeRun: (expectedRunId: string) => void;
  invalidateRun: (expectedRunId: string) => void;
  endRun: (expectedRunId: string) => void;
  isCurrentRun: (expectedRunId: string) => boolean;
  /** 새 실행 시작. 이전 실행의 진행 데이터는 버린다 */
  startRun: (input: StartRunInput) => void;
  continueAnalysis: (expectedRunId: string, jobId: string, guideId: string) => void;
  /** 로그아웃·계정 변경 때 실행을 비운다 */
  clearRun: () => void;
  /** 실행을 통째로 바꾼다. 테스트·개발용 화면이 준비된 실행을 넣을 때 쓴다 */
  replaceRun: (run: RunState) => void;
}

const RunContext = createContext<RunValue | null>(null);

/** 진행 중인 실행. 메모리에만 두고 저장하지 않는다 */
export function RunProvider({ children }: { children: ReactNode }) {
  const [run, setRun] = useState<RunState>(EMPTY_RUN);
  const activeRunId = useRef("");
  const previousRunId = useRef("");

  useLayoutEffect(() => {
    if (previousRunId.current !== run.id) {
      clearFacePhoto(previousRunId.current);
      clearRegisteredGaugeBaseline(previousRunId.current);
    }
    if (run.phase === "completed" || run.phase === "invalidated")
      clearRegisteredGaugeBaseline(run.id);
    // 끝내기·새 실행·로그아웃·무효화는 모두 여기를 지난다. 완료 기록을 남긴 실행의 사진만 남긴다
    if (previousRunId.current !== run.id || run.phase === "invalidated") discardUnsavedStepPhotos();
    previousRunId.current = run.id;
    activeRunId.current = run.phase === "invalidated" ? "" : run.id;
  }, [run.id, run.phase]);
  useEffect(() => () => clearRegisteredGaugeBaseline(), []);

  const isCurrentRun = useCallback((id: string) => !!id && activeRunId.current === id, []);

  const updateRun = useCallback<RunValue["updateRun"]>((patch, expectedRunId) => {
    setRun((prev) =>
      (expectedRunId !== undefined && prev.id !== expectedRunId) || prev.phase === "invalidated"
        ? prev
        : { ...prev, ...(typeof patch === "function" ? patch(prev) : patch) },
    );
  }, []);

  const startRun = useCallback((input: StartRunInput) => {
    clearFacePhoto();
    const next = createRun(input, crypto.randomUUID());
    activeRunId.current = next.id;
    setRun(next);
  }, []);

  const continueAnalysis = useCallback((expectedRunId: string, jobId: string, guideId: string) => {
    setRun((prev) =>
      prev.id !== expectedRunId ? prev : continueAnalysisRun(prev, jobId, guideId),
    );
  }, []);

  const endRun = useCallback((expectedRunId: string) => {
    if (activeRunId.current === expectedRunId) activeRunId.current = "";
    setRun((prev) => (prev.id !== expectedRunId ? prev : EMPTY_RUN));
    clearFacePhoto(expectedRunId);
  }, []);

  const invalidateRun = useCallback((expectedRunId: string) => {
    if (activeRunId.current === expectedRunId) activeRunId.current = "";
    clearFacePhoto(expectedRunId);
    setRun((prev) => (prev.id !== expectedRunId ? prev : invalidated(prev)));
  }, []);

  const bindGuide = useCallback((expectedRunId: string, version: number, picked: VideoItem) => {
    setRun((prev) => {
      if (
        prev.id !== expectedRunId ||
        prev.mode !== "guide" ||
        prev.phase === "invalidated" ||
        prev.guideVersion === version
      )
        return prev;
      if (prev.guideVersion !== null) return invalidated(prev);
      return { ...prev, guideVersion: version, picked };
    });
  }, []);

  const enterTutorial = useCallback((expectedRunId: string, photoOk: boolean) => {
    // captures를 비우므로 남은 사진도 함께 비운다. 상단 바·리포트가 같은 기준을 보게
    resetStepPhotos(expectedRunId);
    setRun((prev) =>
      prev.id !== expectedRunId || prev.phase === "invalidated"
        ? prev
        : { ...prev, photoOk, captures: [], phase: "tutorial" },
    );
  }, []);

  const completeRun = useCallback((expectedRunId: string) => {
    setRun((prev) =>
      prev.id !== expectedRunId || prev.phase !== "tutorial"
        ? prev
        : { ...prev, phase: "completed" },
    );
  }, []);

  const clearRun = useCallback(() => {
    activeRunId.current = "";
    clearFacePhoto();
    setRun(EMPTY_RUN);
  }, []);

  const replaceRun = useCallback((next: RunState) => setRun(next), []);

  const value = useMemo(
    () => ({
      run,
      updateRun,
      startRun,
      continueAnalysis,
      isCurrentRun,
      endRun,
      bindGuide,
      enterTutorial,
      completeRun,
      invalidateRun,
      clearRun,
      replaceRun,
    }),
    [
      run,
      updateRun,
      startRun,
      continueAnalysis,
      isCurrentRun,
      endRun,
      bindGuide,
      enterTutorial,
      completeRun,
      invalidateRun,
      clearRun,
      replaceRun,
    ],
  );

  return <RunContext.Provider value={value}>{children}</RunContext.Provider>;
}

export function useRun() {
  const context = useContext(RunContext);
  if (!context) throw new Error("useRun은 SessionProvider 안에서만 쓸 수 있습니다");
  return context;
}
