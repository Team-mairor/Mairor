"use client";

import { useEffect, useMemo, useState, useSyncExternalStore } from "react";

import { faceBrows, type FaceFrame, saveFaceBrows, subscribeFacePhoto } from "@/features/face";
import { loadFaceMesh, type FaceMesh } from "@/features/overlay";

import { findBrows, fitBrowStep, type Pixels } from "./brow-fit";
import type { GuideStep } from "./types";

/** 지금 영상을 원본 그대로 픽셀로 읽는다. 등록 사진과 같은 순간에 부른다 */
export function readPixels(video: HTMLVideoElement): Pixels | null {
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx || !canvas.width || !canvas.height) return null;
  ctx.drawImage(video, 0, 0);
  return ctx.getImageData(0, 0, canvas.width, canvas.height);
}

/** 등록 사진에서 원래 눈썹을 찾아 그 사진에 붙인다. 실패해도 등록은 그대로 두고 기본 눈썹 가이드를 쓴다 */
export async function saveBrowsFrom(runId: string, photo: Blob, pixels: Pixels, frame: FaceFrame) {
  try {
    const mesh = await loadFaceMesh();
    saveFaceBrows(runId, photo, findBrows(pixels, frame, mesh));
  } catch (e) {
    console.warn("등록 사진에서 눈썹을 찾지 못했습니다", e);
  }
}

/**
 * 눈썹 단계 가이드를 등록 사진의 원래 눈썹 모양·앞머리·꼬리에 맞춘다.
 * 눈썹 분석은 등록을 마친 뒤에 끝나기도 하므로, 결과가 저장되면 그때 다시 맞춘다
 */
export function useBrowFit(step: GuideStep | null, runId: string): GuideStep | null {
  const brows = useSyncExternalStore(
    subscribeFacePhoto,
    () => faceBrows(runId),
    () => null,
  );
  const [mesh, setMesh] = useState<FaceMesh | null>(null);
  useEffect(() => {
    if (!brows) return;
    let live = true;
    loadFaceMesh()
      .then((m) => live && setMesh(m))
      .catch((e) => console.warn("메시를 불러오지 못해 눈썹 가이드를 그대로 씁니다", e));
    return () => {
      live = false;
    };
  }, [brows]);
  return useMemo(
    () => (step && brows && mesh ? fitBrowStep(step, brows, mesh) : step),
    [step, brows, mesh],
  );
}
