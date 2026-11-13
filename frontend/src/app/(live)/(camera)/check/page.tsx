"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { GuideCheck } from "@/features/check";
import { useSession } from "@/features/session";

/** 제품 확인은 실제 승인 가이드 실행에서만 연다. */
export default function CheckPage() {
  const router = useRouter();
  const { state } = useSession();
  const isGuideRun = state.run.mode === "guide";

  useEffect(() => {
    if (!isGuideRun) router.replace("/select");
  }, [isGuideRun, router]);

  return isGuideRun ? <GuideCheck /> : null;
}
