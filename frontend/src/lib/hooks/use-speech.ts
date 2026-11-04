"use client";

import { useEffect } from "react";

/** text가 바뀔 때마다 앞 문장을 끊고 새로 읽는다. null이면 멈춘다 (브라우저 기본 음성 합성) */
export function useSpeech(text: string | null) {
  useEffect(() => {
    if (typeof speechSynthesis === "undefined") return;
    speechSynthesis.cancel();
    if (!text) return;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "ko-KR";
    speechSynthesis.speak(u);
    return () => speechSynthesis.cancel();
  }, [text]);
}
