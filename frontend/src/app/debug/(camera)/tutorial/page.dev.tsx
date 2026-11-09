"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  TutorialCropEditor,
  loadDefaultGuideSet,
  loadGuideArea,
  loadGuideSet,
  resolveSubStep,
  type AreaStatus,
  type GuideStep,
} from "@/features/guide";

/** 한 화면에 보여 줄 가이드. AI 영역은 하위 단계마다 하나다 */
interface Item {
  title: string;
  detail: string;
  step: GuideStep | null;
}

const STATUS_LABEL: Record<AreaStatus, string> = {
  extracted: "영상에서 찾은 영역",
  template: "기본 영역",
  notApplicable: "영역 없음",
  failed: "영역을 찾지 못함",
};

/** 그릴 영역이 없을 때 안내 */
const EMPTY_NOTE: Partial<Record<AreaStatus, string>> = {
  notApplicable: "이 단계는 바를 영역이 없어요",
  failed: "영상에서 바를 곳을 찾지 못했어요. 설명을 보고 따라 해 주세요",
};

/**
 * 튜토리얼 가이드 확인 화면. 기본은 9개 부위 기본 가이드이고,
 * ?guides=경로 는 가이드 파일, ?area=경로 는 AI 가이드 영역 파일을 하위 단계마다 넘겨 본다.
 */
export default function TutorialPage() {
  const [items, setItems] = useState<Item[] | null>(null);
  const [index, setIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [prediction, setPrediction] = useState(0.6);
  const [showStats, setShowStats] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const value = params.get("prediction");
    const area = params.get("area");
    const guides = params.get("guides");
    // 가이드 파일을 못 불러와도 주소창 값은 적용한다. 주소창 값은 브라우저에서만 읽을 수 있다
    /* eslint-disable react-hooks/set-state-in-effect */
    if (value === "off") setPrediction(0);
    else if (value !== null && Number.isFinite(Number(value)))
      setPrediction(Math.max(0, Math.min(1, Number(value))));
    setShowStats(params.has("stats"));
    /* eslint-enable react-hooks/set-state-in-effect */
    const load = async (): Promise<Item[]> => {
      if (area) {
        const [data, defaults] = await Promise.all([loadGuideArea(area), loadDefaultGuideSet()]);
        return data.steps.flatMap((step) =>
          step.subSteps.map((sub) => {
            const resolved = resolveSubStep(sub, defaults);
            const reasons = sub.reasons.length ? ` (${sub.reasons.join(", ")})` : "";
            return {
              title: resolved?.title || EMPTY_NOTE[sub.status] || STATUS_LABEL[sub.status],
              detail: `${sub.subStepId} · ${step.makeup} · ${STATUS_LABEL[sub.status]}${reasons}`,
              step: resolved,
            };
          }),
        );
      }
      const set = await (guides ? loadGuideSet(guides) : loadDefaultGuideSet());
      return set.steps.map((step) => ({ title: step.title, detail: step.stepId, step }));
    };
    load()
      .then(setItems)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const list = items ?? [];
  const item = list[index] ?? null;

  return (
    <main className="relative flex flex-1 flex-col gap-4 bg-background p-6">
      <header className="relative rounded-lg bg-black/50 px-4 py-3 text-white">
        {item ? (
          <>
            <p className="text-sm opacity-80">
              {index + 1} / {list.length} · {item.detail}
            </p>
            <h1 className="text-lg font-semibold">{item.title}</h1>
          </>
        ) : (
          <h1 className="text-lg font-semibold">
            {error ?? (items ? "이 영상에는 가이드가 없어요" : "가이드를 불러오는 중")}
          </h1>
        )}
      </header>

      <TutorialCropEditor
        step={item?.step ?? null}
        predictionStrength={prediction}
        showStats={showStats}
      />

      <nav className="relative flex items-center justify-between gap-3">
        <label className="rounded bg-black/70 p-2 text-sm text-white">
          예측 {prediction.toFixed(1)}
          <input
            aria-label="위치 예측 강도"
            type="range"
            min="0"
            max="1"
            step="0.1"
            value={prediction}
            onChange={(event) => setPrediction(Number(event.target.value))}
          />
        </label>
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
            disabled={index >= list.length - 1}
            onClick={() => setIndex((i) => Math.min(list.length - 1, i + 1))}
          >
            다음
          </Button>
        </div>
      </nav>
    </main>
  );
}
