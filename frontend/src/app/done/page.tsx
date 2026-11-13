"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { GuideDone } from "@/features/report";
import { useSession } from "@/features/session";

/** 실행 ID가 있는 실제 가이드 완료 화면만 허용한다. */
export default function DonePage() {
  const router = useRouter();
  const { state } = useSession();
  const isGuideRun = state.run.mode === "guide" && !!state.run.executionId;

  useEffect(() => {
    if (!isGuideRun) router.replace("/select");
  }, [isGuideRun, router]);

  return isGuideRun ? <GuideDone /> : null;
}
