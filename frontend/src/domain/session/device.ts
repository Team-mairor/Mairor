"use client";

import { useCallback } from "react";

import { STORAGE_KEYS, isObject } from "./storage";
import { createStore } from "./store";

/** 이 기기에서 본 안내. 로그아웃해도 지우지 않는다 */
export interface DeviceState {
  onboarded: boolean;
  tutSeen: boolean;
}

const EMPTY_DEVICE: DeviceState = { onboarded: false, tutSeen: false };

function parseDevice(raw: unknown): DeviceState | undefined {
  if (!isObject(raw)) return undefined;
  return { onboarded: raw.onboarded === true, tutSeen: raw.tutSeen === true };
}

export const deviceStore = createStore("useDevice", STORAGE_KEYS.device, EMPTY_DEVICE, parseDevice);

export function useDevice() {
  const { value, set } = deviceStore.useStore();
  const markOnboarded = useCallback(() => set((prev) => ({ ...prev, onboarded: true })), [set]);
  const markTutSeen = useCallback(() => set((prev) => ({ ...prev, tutSeen: true })), [set]);
  return { ...value, markOnboarded, markTutSeen };
}
