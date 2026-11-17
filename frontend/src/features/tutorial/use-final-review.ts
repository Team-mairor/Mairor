"use client";

import { useState } from "react";

import type { StepPhoto } from "@/domain/session";

/**
 * 마지막 사진은 리포트 대표 사진이라 저장 전에 한 번 보여 주고 다시 찍을 수 있게 한다.
 * 저장에 실패하면 사진을 그대로 두어 다시 시도할 수 있다
 */
export function useFinalReview({ save }: { save: (photo: StepPhoto) => Promise<void> }) {
  const [photo, setPhoto] = useState<StepPhoto | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);

  /** 방금 찍은 사진을 확인 화면에 올린다 */
  const begin = (next: StepPhoto) => {
    setError(null);
    setPhoto(next);
  };

  const confirm = async () => {
    if (!photo || saving) return;
    setSaving(true);
    setError(null);
    try {
      await save(photo);
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  };

  /** 확인 화면을 닫고 다시 찍는다. 저장 중에는 닫지 않는다 */
  const retake = () => {
    if (saving) return;
    setPhoto(null);
    setError(null);
  };

  /** 단계를 옮길 때 확인 화면을 정리한다 */
  const reset = () => {
    setPhoto(null);
    setError(null);
  };

  return { photo, saving, error, begin, confirm, retake, reset };
}
