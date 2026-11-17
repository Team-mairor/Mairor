"use client";

import { useEffect, useRef, useState } from "react";

import { isTooDark, isTooDarkReleased, TOO_DARK_HOLD_MS, type GaugeDisplay } from "@/domain/gauge";

/**
 * 너무 진하게 발라 멈추고 확인할 때를 알린다. 진한 상태가 잠시 이어져야 열고,
 * 막대가 충분히 내려오면 저절로 닫힌다(「확인했어요」로도 닫을 수 있다).
 * 한 번 알린 뒤에는 막대가 내려왔다가 다시 넘을 때만 다시 연다. 단계마다 새로 시작한다
 */
export function useTooDarkNotice({
  display,
  enabled,
  stepKey,
}: {
  display: GaugeDisplay | null;
  enabled: boolean;
  stepKey: string;
}) {
  const [openKey, setOpenKey] = useState<string | null>(null);
  /** 이미 알린 단계. 막대가 내려오면 풀어 다시 알릴 수 있게 한다 */
  const notified = useRef<string | null>(null);
  const over = enabled && isTooDark(display);
  const released = isTooDarkReleased(display);

  useEffect(() => {
    if (!released) return;
    if (notified.current === stepKey) notified.current = null;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 막대가 충분히 내려오면 열려 있던 창을 닫는다
    setOpenKey((key) => (key === stepKey ? null : key));
  }, [released, stepKey]);

  useEffect(() => {
    if (!over || notified.current === stepKey) return;
    const timer = setTimeout(() => {
      notified.current = stepKey;
      setOpenKey(stepKey);
    }, TOO_DARK_HOLD_MS);
    return () => clearTimeout(timer);
  }, [over, stepKey]);

  return { open: openKey === stepKey, confirm: () => setOpenKey(null) };
}
