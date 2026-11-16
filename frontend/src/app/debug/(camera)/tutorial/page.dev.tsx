"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { useCamera, useFaceFrame, type FaceBrows, type FaceFrame } from "@/features/face";
import { GaugeDebug, useGaugeBaseline, useGaugeMeasure } from "@/features/gauge";
import {
  fitBrowStep,
  browSpans,
  findBrows,
  TutorialCropEditor,
  loadDefaultGuideSet,
  loadGuideArea,
  loadGuideSet,
  readPixels,
  resolveSubStep,
  type AreaGuideSet,
  type AreaStatus,
  type AreaSubStep,
  type GuideStep,
} from "@/features/guide";
import { loadFaceMesh, type FaceMesh } from "@/features/overlay";

/** 한 화면에 보여 줄 가이드. AI 영역은 하위 단계마다 하나다 */
interface Item {
  title: string;
  detail: string;
  step: GuideStep | null;
  /** AI 영역 파일의 하위 단계와 화장 종류. 게이지를 잴 때 쓴다 */
  sub?: AreaSubStep;
  makeup?: string;
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
 * "원래 눈썹 찾기"는 지금 카메라 화면을 등록 사진처럼 써서 눈썹 가이드를 원래 눈썹 모양·앞머리·꼬리에 맞춘다.
 * "맨얼굴 기준 잡기"는 튜토리얼처럼 게이지 맨얼굴 기준을 모으고 카메라 잠금 결과와 칸 색 읽는 시간을 띄운다.
 * 기준을 잡은 뒤 게이지 기준이 있는 하위 단계(?area=…local_01.json의 s17-1 등)에서는 그 영역을 재 잰 값을 띄운다.
 */
export default function TutorialPage() {
  const [items, setItems] = useState<Item[] | null>(null);
  const [index, setIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [prediction, setPrediction] = useState(0.6);
  const [showStats, setShowStats] = useState(false);
  // 등록 사진 대신 지금 카메라 화면으로 원래 눈썹을 찾아 눈썹 가이드를 맞춰 본다
  const { videoRef } = useCamera();
  const frameRef = useRef<FaceFrame | null>(null);
  useFaceFrame((frame) => {
    frameRef.current = frame;
  });
  const [mesh, setMesh] = useState<FaceMesh | null>(null);
  const [brows, setBrows] = useState<FaceBrows | null>(null);
  const [browNote, setBrowNote] = useState("");
  useEffect(() => {
    loadFaceMesh()
      .then(setMesh)
      .catch((e) => setBrowNote(`메시를 불러오지 못했어요: ${String(e)}`));
  }, []);
  const findOwnBrows = () => {
    const video = videoRef.current;
    const frame = frameRef.current;
    if (!video || !mesh || !frame || frame.trackingState !== "tracking") {
      setBrowNote("정면 얼굴이 잡힐 때 다시 눌러 주세요");
      return;
    }
    const pixels = readPixels(video);
    if (!pixels) return setBrowNote("카메라 영상을 읽지 못했어요");
    const found = findBrows(pixels, frame, mesh);
    setBrows(found);
    // 랜드마크 눈썹 앞머리·꼬리에서 얼마나 옮겼는지(눈썹 길이 %). 앞머리 +는 안쪽(꼬리 쪽), 꼬리 +는 바깥쪽
    const spans = browSpans(found, mesh);
    const pct = (v: number) => `${v >= 0 ? "+" : ""}${Math.round(v * 100)}%`;
    const note = (["rightBrow", "leftBrow"] as const)
      .map((side) => {
        const name = side === "rightBrow" ? "오른쪽" : "왼쪽";
        const span = spans[side];
        if (span) return `${name} 앞머리 ${pct(span.head)} 꼬리 ${pct(span.tail - 1)}`;
        return found[side] ? `${name} 길이가 이상해 안 맞춤` : `${name} 못 찾음`;
      })
      .join(" · ");
    setBrowNote(note);
  };

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
            const resolved = resolveSubStep(sub, defaults, step.makeup);
            const reasons = sub.reasons.length ? ` (${sub.reasons.join(", ")})` : "";
            return {
              title: resolved?.title || EMPTY_NOTE[sub.status] || STATUS_LABEL[sub.status],
              detail: `${sub.subStepId} · ${step.makeup} · ${STATUS_LABEL[sub.status]}${reasons}`,
              step: resolved,
              sub,
              makeup: step.makeup,
            };
          }),
        );
      }
      const set = await (guides ? loadGuideSet(guides) : loadDefaultGuideSet());
      return set.steps.map((step) => ({ title: step.title, detail: step.stepId, step }));
    };
    // ?sub=하위 단계 ID 로 그 하위 단계부터 본다
    const sub = params.get("sub");
    load()
      .then((loaded) => {
        setItems(loaded);
        const at = sub ? loaded.findIndex((x) => x.detail.startsWith(`${sub} `)) : -1;
        if (at >= 0) setIndex(at);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const list = items ?? [];
  const item = list[index] ?? null;
  const step = useMemo(
    () => (item?.step && mesh ? fitBrowStep(item.step, brows, mesh) : (item?.step ?? null)),
    [item, mesh, brows],
  );

  return (
    // 스크롤 없이 한 화면에 맞춘다
    <main className="relative flex min-h-0 flex-1 flex-col gap-2 overflow-hidden bg-background p-3">
      <header className="relative shrink-0 rounded-lg bg-black/50 px-3 py-2 text-white">
        <h1 className="truncate text-base font-semibold">
          {item ? (
            <>
              {index + 1} / {list.length} · {item.title}
              <span className="ml-2 text-xs font-normal opacity-80">{item.detail}</span>
            </>
          ) : (
            (error ?? (items ? "이 영상에는 가이드가 없어요" : "가이드를 불러오는 중"))
          )}
        </h1>
      </header>

      <TutorialCropEditor
        step={step}
        predictionStrength={prediction}
        showStats={showStats}
        footer={(reset) => (
          // 아래 양쪽 개발용 버튼을 피한다
          <nav className="relative flex shrink-0 items-center justify-between gap-3 px-14">
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
            <div className="flex items-center gap-3">
              <Button size="lg" variant="outline" onClick={findOwnBrows}>
                원래 눈썹 찾기
              </Button>
              {brows && (
                <Button
                  size="lg"
                  variant="ghost"
                  onClick={() => {
                    setBrows(null);
                    setBrowNote("");
                  }}
                >
                  지우기
                </Button>
              )}
              {browNote && (
                <span className="rounded bg-black/70 p-2 text-sm text-white">{browNote}</span>
              )}
            </div>
            <GaugeBaselineCheck item={item} />
            <div className="flex gap-3">
              <Button size="lg" variant="outline" asChild>
                <Link href="/debug/preview">처음으로</Link>
              </Button>
              {reset}
            </div>
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
        )}
      />
    </main>
  );
}

const NO_SETS: AreaGuideSet[] = [];

/**
 * 게이지 맨얼굴 기준을 튜토리얼과 같은 방법으로 모아 본다. 누를 때마다 새로 모은다.
 * 기준을 잡은 뒤 지금 하위 단계에 게이지 기준(gauge)이 있으면 그 영역을 이어서 재 잰 값을 띄운다
 */
function GaugeBaselineCheck({ item }: { item: Item | null }) {
  const [run, setRun] = useState<string | null>(null);
  const baseline = useGaugeBaseline({ runId: run ?? "", step: 0, collecting: run !== null });
  const { status } = baseline;
  const sub = item?.sub;
  const guideSets = sub?.guideSets ?? NO_SETS;
  const measured = useGaugeMeasure({
    active: !!status.bare && !!sub?.gauge,
    key: run && sub ? `${run}:${sub.subStepId}` : null,
    makeup: item?.makeup ?? "",
    gauge: sub?.gauge ?? null,
    guideSets,
    madeSets: guideSets,
    start: status.bare,
    white: status.white,
    debug: true,
  });
  const lock = status.lock
    ? Object.entries(status.lock)
        .map(([name, result]) => `${name} ${result}`)
        .join(" · ")
    : "잠그기 전";
  const note = !run
    ? ""
    : [
        status.center === null ? "정면 찾는 중" : `정면 pitch ${status.center.toFixed(2)}`,
        status.quality &&
          `yaw ${status.quality.yaw.toFixed(2)} pitch ${status.quality.pitch.toFixed(2)} roll ${status.quality.roll.toFixed(2)} 눈 ${status.quality.eyes.toFixed(2)} (점 6개 ${status.quality.aspect.toFixed(2)})`,
        status.bare ? "맨얼굴 기준 완료" : `사진 ${status.frames}/15`,
        status.readMs === null ? null : `칸 읽기 ${status.readMs.toFixed(1)}ms`,
        lock,
        status.lockMs === null ? null : `잠그기 ${(status.lockMs / 1000).toFixed(1)}초`,
      ]
        .filter(Boolean)
        .join(" · ");
  return (
    <div className="flex items-center gap-3">
      <Button size="lg" variant="outline" onClick={() => setRun(String(Date.now()))}>
        맨얼굴 기준 잡기
      </Button>
      {note && <span className="rounded bg-black/70 p-2 text-sm text-white">{note}</span>}
      {status.bare && sub?.gauge && (
        <GaugeDebug
          baseline={status}
          reading={measured.reading}
          display={measured.display}
          areas={measured.areas.map((a) => a.cells)}
          made={measured.made}
        />
      )}
    </div>
  );
}
