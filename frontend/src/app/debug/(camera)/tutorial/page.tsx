"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { GuideOverlay, loadDefaultGuideSet, loadGuideSet, type GuideSet } from "@/features/guide";

export default function TutorialPage() {
  // 레시피 연동 전까지는 기본 가이드를 쓰고, ?guides=경로 로 가이드 파일을 바꿔 본다.
  const [guideSet, setGuideSet] = useState<GuideSet | null>(null);
  const [index, setIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const url = new URLSearchParams(window.location.search).get("guides");
    (url ? loadGuideSet(url) : loadDefaultGuideSet())
      .then(setGuideSet)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const steps = guideSet?.steps ?? [];
  const step = steps[index] ?? null;

  return (
    <main className="relative flex flex-1 flex-col justify-between p-6">
      <GuideOverlay step={step} />

      <header className="relative rounded-lg bg-black/50 px-4 py-3 text-white">
        {step ? (
          <>
            <p className="text-sm opacity-80">
              {index + 1} / {steps.length}
            </p>
            <h1 className="text-lg font-semibold">{step.title}</h1>
          </>
        ) : (
          <h1 className="text-lg font-semibold">
            {error ?? (guideSet ? "이 영상에는 가이드가 없어요" : "가이드를 불러오는 중")}
          </h1>
        )}
      </header>

      <nav className="relative flex items-center justify-between gap-3">
        <Button size="lg" variant="outline" asChild>
          <Link href="/debug/preview">처음으로</Link>
        </Button>
        <div className="flex gap-3">
          <Button
            size="lg"
            variant="secondary"
            disabled={index === 0}
            onClick={() => setIndex((i) => Math.max(0, i - 1))}
          >
            이전
          </Button>
          <Button
            size="lg"
            disabled={index >= steps.length - 1}
            onClick={() => setIndex((i) => Math.min(steps.length - 1, i + 1))}
          >
            다음
          </Button>
        </div>
      </nav>
    </main>
  );
}
