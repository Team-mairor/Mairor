"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { GuideStatus } from "@/components/guide-status";
import { toGuideArea } from "@/domain/guide";
import { useGuide, useRunQuery } from "@/domain/guide-run";
import { useRun } from "@/domain/session";
import { checkGuideArea, type GuideArea } from "@/vision/guide";

import { TutorialRun } from "./tutorial-run";
import { stepsOf } from "./tutorial-steps";

/**
 * 10 튜토리얼.
 * 승인된 가이드 조회 API가 제공하는 단계·설명·영역으로 실행한다.
 */
export function TutorialEntry() {
  const query = useRunQuery();
  const { run } = useRun();
  const router = useRouter();
  useEffect(() => {
    if (run.mode !== "guide") router.replace("/select");
  }, [router, run.mode]);
  if (!query) return null;
  return run.mode === "guide" ? <GuideTutorial /> : null;
}

/** 가이드를 불러오는 상태를 안내하고, 준비되면 단계와 영역으로 튜토리얼을 연다 */
function GuideTutorial() {
  const router = useRouter();
  const { load, retry } = useGuide();
  const guide = load.status === "ready" ? load.guide : null;
  const steps = useMemo(() => (guide ? stepsOf(guide) : []), [guide]);
  const [area, setArea] = useState<GuideArea | null>(null);

  useEffect(() => {
    const raw = guide && toGuideArea(guide);
    if (!raw) return;
    let alive = true;
    // 영역을 쓸 수 없으면(지원하지 않는 메시 판 등) 설명과 기본 가이드로 진행한다
    checkGuideArea(raw, `guide ${guide.guideId}`)
      .then((checked) => alive && setArea(checked))
      .catch((e) => console.warn("가이드 영역을 쓸 수 없어 기본 가이드로 보여 줍니다", e));
    return () => {
      alive = false;
    };
  }, [guide]);

  const home = { label: "홈으로", onClick: () => router.push("/home") };
  switch (load.status) {
    case "loading":
      return <GuideStatus title="가이드를 불러오고 있어요" />;
    case "invalidId":
      return <GuideStatus title="가이드 주소가 올바르지 않아요" action={home} />;
    case "invalidated":
    case "notFound":
      return (
        <GuideStatus
          title="가이드가 없거나 아직 이용할 수 없어요"
          body="분석이 끝나고 내려지지 않은 가이드만 따라 할 수 있어요."
          action={home}
        />
      );
    case "login":
      return (
        <GuideStatus
          title="로그인이 필요해요"
          action={{ label: "로그인하기", onClick: () => router.push("/login") }}
        />
      );
    case "error":
      return (
        <GuideStatus
          title="가이드를 불러오지 못했어요"
          body={load.message}
          action={{
            label: "다시 시도",
            onClick: () => {
              void retry();
            },
          }}
        />
      );
    case "ready":
      if (!steps.length)
        return <GuideStatus title="따라 할 단계가 없는 가이드예요" action={home} />;
      return <TutorialRun steps={steps} area={area} />;
  }
}
