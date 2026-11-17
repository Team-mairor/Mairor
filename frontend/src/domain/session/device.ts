"use client";

import { useCallback } from "react";

import { STORAGE_KEYS, isObject } from "./storage";
import { createStore } from "./store";

/** 이 기기에서 본 안내. 온보딩·튜토리얼 안내는 로그아웃해도 지우지 않는다 */
export interface DeviceState {
  onboarded: boolean;
  tutSeen: boolean;
  /** 이번 로그인에서 첫 진입 안내를 본 화면 id. 다른 로그인이 시작되면 signIn이 비운다 */
  toured: string[];
}

export const EMPTY_DEVICE: DeviceState = { onboarded: false, tutSeen: false, toured: [] };

function parseDevice(raw: unknown): DeviceState | undefined {
  if (!isObject(raw)) return undefined;
  return {
    onboarded: raw.onboarded === true,
    tutSeen: raw.tutSeen === true,
    toured: Array.isArray(raw.toured)
      ? raw.toured.filter((id): id is string => typeof id === "string")
      : [],
  };
}

export const deviceStore = createStore("useDevice", STORAGE_KEYS.device, EMPTY_DEVICE, parseDevice);

export function useDevice() {
  const { value, set } = deviceStore.useStore();
  const markOnboarded = useCallback(() => set((prev) => ({ ...prev, onboarded: true })), [set]);
  const markTutSeen = useCallback(() => set((prev) => ({ ...prev, tutSeen: true })), [set]);
  const markToured = useCallback(
    (id: string) => set((prev) => ({ ...prev, toured: [...prev.toured, id] })),
    [set],
  );
  return { ...value, markOnboarded, markTutSeen, markToured };
}
