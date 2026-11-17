"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useRun } from "@/domain/session";
import { GuideCheck } from "@/features/check";

/** 제품 확인은 실제 승인 가이드 실행에서만 연다. */
export default function CheckPage() {
  const router = useRouter();
  const { run } = useRun();
  const isGuideRun = run.mode === "guide";

  useEffect(() => {
    if (!isGuideRun) router.replace("/select");
  }, [isGuideRun, router]);

  return isGuideRun ? <GuideCheck /> : null;
}
