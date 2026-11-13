"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { GuidePreview } from "@/features/preview";
import { useSession } from "@/features/session";

/** 미리보기는 실제 승인 가이드 실행에서만 연다. */
export default function PreviewPage() {
  const router = useRouter();
  const { state } = useSession();
  const isGuideRun = state.run.mode === "guide";

  useEffect(() => {
    if (!isGuideRun) router.replace("/select");
  }, [isGuideRun, router]);

  return isGuideRun ? <GuidePreview /> : null;
}
