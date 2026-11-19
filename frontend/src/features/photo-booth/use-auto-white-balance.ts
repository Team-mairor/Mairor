"use client";

import { useEffect, type RefObject } from "react";

import { WHITE_BALANCE_IDS } from "./beauty-filter";
import {
  estimateSkinGains,
  gainsToMatrix,
  NEUTRAL_GAINS,
  smoothGains,
  type WhiteBalanceGains,
} from "./white-balance";

const SAMPLE_W = 64;
const SAMPLE_H = 48;
const INTERVAL_MS = 250;
/** 얼굴이 놓이는 화면 가운데만 읽는다. 가장자리 배경을 피부색으로 오인하지 않게 한다. */
const CENTER = { x: 0.2, y: 0.15, w: 0.6, h: 0.7 };

/** 다시 찍으러 돌아와도 처음부터 보정된 색으로 시작하도록 마지막 값을 기억한다. */
let lastGains: WhiteBalanceGains | null = null;

function applyGains(gains: WhiteBalanceGains) {
  const values = gainsToMatrix(gains);
  for (const id of WHITE_BALANCE_IDS) document.getElementById(id)?.setAttribute("values", values);
}

/** 카메라 영상에서 피부색을 읽어 노란 기운을 일정하게 맞춘다. 미리보기와 저장 사진이 같은 필터를 쓴다. */
export function useAutoWhiteBalance(videoRef: RefObject<HTMLVideoElement | null>, active: boolean) {
  useEffect(() => {
    if (!active) return;
    const canvas = document.createElement("canvas");
    canvas.width = SAMPLE_W;
    canvas.height = SAMPLE_H;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) return;

    let gains = lastGains ?? NEUTRAL_GAINS;
    applyGains(gains);

    const timer = window.setInterval(() => {
      const video = videoRef.current;
      if (!video || !video.videoWidth || !video.videoHeight) return;
      try {
        context.drawImage(
          video,
          video.videoWidth * CENTER.x,
          video.videoHeight * CENTER.y,
          video.videoWidth * CENTER.w,
          video.videoHeight * CENTER.h,
          0,
          0,
          SAMPLE_W,
          SAMPLE_H,
        );
        const next = estimateSkinGains(context.getImageData(0, 0, SAMPLE_W, SAMPLE_H).data);
        if (!next) return;
        gains = lastGains ? smoothGains(gains, next) : next;
        lastGains = gains;
        applyGains(gains);
      } catch {
        // 읽지 못하면 이전 배율을 유지한다
      }
    }, INTERVAL_MS);

    return () => window.clearInterval(timer);
  }, [videoRef, active]);
}
