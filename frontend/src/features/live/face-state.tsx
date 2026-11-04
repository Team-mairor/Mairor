"use client";

import { createContext, useContext, type ReactNode } from "react";

import { useTrackingIssue, type TrackingIssue } from "@/features/face";

interface FaceState {
  face: boolean;
  /** 공통 추적 판정. 없으면 null */
  issue: TrackingIssue | null;
}

const FaceStateContext = createContext<FaceState | null>(null);

/** 추적 상태 요약을 카메라 화면 전체가 한 번만 계산해 나눠 쓴다 (프레임 리스너 1개) */
export function FaceStateProvider({ children }: { children: ReactNode }) {
  const issue = useTrackingIssue();
  const face = issue !== "lost";
  return <FaceStateContext.Provider value={{ face, issue }}>{children}</FaceStateContext.Provider>;
}

/** 추적 상태 요약. 프레임마다가 아니라 바뀔 때만 리렌더한다 */
export function useFaceState() {
  const context = useContext(FaceStateContext);
  if (!context) throw new Error("useFaceState는 FaceStateProvider 안에서만 쓸 수 있습니다");
  return context;
}
