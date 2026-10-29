"use client";

import { useState } from "react";

import { useFaceFrame } from "./camera-provider";
import { KEY_REGIONS } from "./tracking-rules";
import { MIN_IN_FRAME_RATIO } from "./visibility";
import type { FaceFrame } from "./types";

/** 가이드·화장이 숨겨졌거나 색이 정확하지 않은 이유 */
export type TrackingIssue = "lost" | "turned" | "out-of-frame" | "far";

/** 얼굴 폭이 영상 폭의 이 비율보다 작으면 너무 멀다 */
export const MIN_FACE_WIDTH_RATIO = 0.4;

/** 이유별 안내 문구(title)와 조정 방법(desc) */
export const TRACKING_ISSUE_TEXT: Record<TrackingIssue, { title: string; desc: string }> = {
  lost: {
    title: "얼굴이 화면을 벗어났어요",
    desc: "화면 가운데로 돌아오면 메이크업이 다시 보여요.",
  },
  turned: {
    title: "고개를 정면으로 돌려 주세요",
    desc: "옆으로 많이 돌리면 색이 어긋나서 잠시 숨겼어요.",
  },
  // 화면 밖으로 잘린 경우와 하단 패널에 가린 경우가 같은 판정이라, 둘 다 맞는 문구로 쓴다
  "out-of-frame": {
    title: "얼굴 일부가 잘리거나 가려졌어요",
    desc: "얼굴 전체가 화면 가운데에 보이게 해 주세요.",
  },
  far: { title: "조금 더 가까이 와 주세요", desc: "얼굴이 작게 보이면 색이 정확하지 않아요." },
};

/**
 * 지금 프레임의 추적 문제. 없으면 null.
 * lost·turned·out-of-frame은 가이드·화장을 숨긴 상태이고, far는 숨기지 않지만 색이 정확하지 않다.
 */
export function trackingIssue(frame: FaceFrame | null): TrackingIssue | null {
  if (!frame || frame.trackingState === "lost") return "lost";
  if (frame.trackingState === "degraded") {
    // 돌아간 부위와 잘린 부위 중 많은 쪽을 먼저 안내한다. 같으면 뒤로 물러나는 쪽이 먼저다.
    const v = KEY_REGIONS.map((name) => frame.regionVisibility[name]);
    const turned = v.filter((r) => !r.facing).length;
    const cut = v.filter((r) => r.facing && r.inFrameRatio < MIN_IN_FRAME_RATIO).length;
    return turned > cut ? "turned" : "out-of-frame";
  }
  return faceWidthRatio(frame) < MIN_FACE_WIDTH_RATIO ? "far" : null;
}

/** 얼굴 폭 / 영상 폭 */
export function faceWidthRatio(frame: FaceFrame): number {
  return (frame.regions.faceOval.width * frame.iod) / frame.imageSize.width;
}

/**
 * CameraProvider 안에서 추적 문제가 바뀔 때만 다시 그린다. 얼굴을 처음 찾기 전에는 lost이고,
 * 잠깐 놓친 동안(hold)에는 직전 값을 유지한다.
 */
export function useTrackingIssue(): TrackingIssue | null {
  const [issue, setIssue] = useState<TrackingIssue | null>("lost");
  useFaceFrame((frame) => {
    if (frame?.trackingState === "hold") return;
    const next = trackingIssue(frame);
    setIssue((prev) => (prev === next ? prev : next));
  });
  return issue;
}
