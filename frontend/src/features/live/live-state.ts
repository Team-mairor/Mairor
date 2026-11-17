"use client";

import { useSyncExternalStore } from "react";

import { isRetryable, trackingIssueText, useCamera, type TrackingIssue } from "@/features/face";
import { isMirror, subscribeMirror } from "@/lib/mirror";

import { useFaceState } from "./face-state";
import { ALERT, CAMERA_ERROR_TEXT, type LiveAlert } from "./messages";

export interface LiveNoteData {
  title: string;
  desc: string;
  /** 다시 시도 버튼 글자. 카메라 오류일 때만 */
  retry?: string;
  onRetry?: () => void;
  /** 카메라가 켜져 있어 인식 알림을 보여 주는 중 */
  live: boolean;
  face: boolean;
}

/** 카메라 오류 안내. 오류가 없으면 null */
export function useCameraErrorNote(face: boolean): LiveNoteData | null {
  const { status, error, start } = useCamera();
  if (status !== "error" || !error) return null;
  const [t, d] = CAMERA_ERROR_TEXT[error.kind] ?? CAMERA_ERROR_TEXT.unknown!;
  // CameraErrorView와 같은 기준: 다시 시도해도 결과가 같은 오류는 버튼을 숨긴다
  const retryable = isRetryable(error.kind);
  return {
    title: t,
    desc: d,
    retry: retryable ? (error.kind === "tracker-failed" ? "다시 시도" : "카메라 켜기") : undefined,
    onRetry: retryable ? () => void start() : undefined,
    live: false,
    face,
  };
}

/** 가이드·게이지를 멈춘 이유. null이면 정상 */
export type LiveReason = LiveAlert | TrackingIssue | "error" | "starting";

export interface LiveState {
  /** 보여 줄 안내 카드. 없으면 null */
  note: LiveNoteData | null;
  /** 얼굴 위에 메이크업·가이드를 그려도 되는 상태 (카메라 준비 + 얼굴 있음 + 알림 없음) */
  canRender: boolean;
  /** 진하기를 잴 수 있는 상태 (canRender + 거리 충분) */
  canMeasure: boolean;
  reason: LiveReason | null;
}

/**
 * 현재 보여 줄 안내와 그릴 수 있는지 여부. 카메라 오류 > 준비 중 > 확인용 알림 > 추적 문제.
 * 카메라 화면(제품 체크·튜토리얼)은 이 값으로 숨김·측정 불가를 판단한다
 */
export function useLiveState(
  alert?: LiveAlert | null,
  /** 화면별 추가 판정. 공통 추적 판정에 문제가 없을 때만 쓴다 */
  extraIssue?: TrackingIssue | null,
  /** 튜토리얼은 현재 단계 부위의 판정으로 공통 얼굴 전체 판정을 대체한다. */
  trackingOverride?: { issue: TrackingIssue | null },
): LiveState {
  const { status } = useCamera();
  const { face, issue: trackIssue } = useFaceState();
  const mirror = useSyncExternalStore(subscribeMirror, isMirror, () => false);
  const issue = trackingOverride ? trackingOverride.issue : (trackIssue ?? extraIssue ?? null);
  const err = useCameraErrorNote(face);
  const off = { canRender: false, canMeasure: false };
  if (err) return { note: err, ...off, reason: "error" };
  if (status !== "ready")
    return {
      note: { title: "카메라를 켜는 중이에요", desc: "잠시만 기다려 주세요.", live: false, face },
      ...off,
      reason: "starting",
    };
  if (alert)
    return {
      note: { title: ALERT[alert][0], desc: ALERT[alert][1], live: true, face },
      // 실제 거리 감지와 같은 기준: 멀 때는 화장·가이드를 두고 측정만 멈춘다
      canRender: alert === "far",
      canMeasure: false,
      reason: alert,
    };
  if (issue)
    return {
      note: { ...trackingIssueText(issue, mirror), live: true, face },
      // 너무 멀 때만 그리고, 나머지는 가이드·화장을 숨긴 상태다
      canRender: issue === "far",
      canMeasure: false,
      reason: issue,
    };
  return { note: null, canRender: true, canMeasure: true, reason: null };
}

/** 안내 카드만 필요할 때 */
export function useLiveNote(alert?: LiveAlert | null): LiveNoteData | null {
  return useLiveState(alert).note;
}
