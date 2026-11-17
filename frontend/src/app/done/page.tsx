"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useRun } from "@/domain/session";
import { GuideDone } from "@/features/report";

/** 실행 ID가 있는 실제 가이드 완료 화면만 허용한다. */
export default function DonePage() {
  const router = useRouter();
  const { run } = useRun();
  const isGuideRun = run.mode === "guide" && !!run.executionId;

  useEffect(() => {
    if (!isGuideRun) router.replace("/select");
  }, [isGuideRun, router]);

  return isGuideRun ? <GuideDone /> : null;
}
