"use client";

import { ArrowRight, Check } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

/** 촬영 조건. 앞 4개 필수, 맨얼굴은 권장 (CAMERA-005) */
const CONDITIONS: [label: string, hint: string][] = [
  ["밝고 고른 조명", "조명이 어둡거나 한쪽으로 치우쳐 있어요"],
  ["원 안 · 적정 거리", "얼굴을 원 안에 맞춰 주세요"],
  ["정면 · 무표정", "고개를 정면으로 바로 하고 입을 다물어 주세요"],
  ["가림 없음", "앞머리를 넘기고 안경을 벗어 주세요"],
  ["맨얼굴", "메이크업이 감지됐어요. 지운 뒤 촬영하면 더 정확해요"],
];
const TIPS = ["밝고 고른 조명", "정면 · 이마 드러내기", "맨얼굴이면 더 정확해요"];

type Stage = "ready" | "scan" | "done";

/**
 * 얼굴 등록 모달 (CAMERA-005 · VIDEO-004). 안내 → 조건 체크 → 자동 촬영 → 완료.
 * ponytail: 조건 판정·촬영은 타이머로 흉내 낸다. 실시간 조건 체크(조명·거리·정면·가림)가 생기면 타이머를 그 결과로 바꾼다.
 */
export function FaceRegisterModal({
  pct,
  barText,
  replay,
  onDone,
  onLater,
}: {
  /** 분석 진행률 (상단 바) */
  pct: number;
  barText: string;
  replay: boolean;
  onDone: () => void;
  onLater: () => void;
}) {
  const [step, setStep] = useState<"intro" | "cam">("intro");
  const [stage, setStage] = useState<Stage>("ready");
  const [ok, setOk] = useState(0);
  const [scan, setScan] = useState(0);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const clear = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };
  useEffect(() => clear, []);

  const start = () => {
    clear();
    setStep("cam");
    setStage("ready");
    setOk(0);
    setScan(0);
    // 조건 4개가 차례로 맞는 연출 → 1.4초 뒤 촬영
    for (let i = 1; i <= 4; i++) timers.current.push(setTimeout(() => setOk(i), 520 * i));
    timers.current.push(
      setTimeout(
        () => {
          setStage("scan");
          for (let p = 1; p <= 100; p++) {
            timers.current.push(
              setTimeout(() => {
                setScan(p);
                if (p === 100) setStage("done");
              }, 70 * p),
            );
          }
        },
        520 * 4 + 1400,
      ),
    );
  };

  const passed = ok >= 4;
  const title =
    stage === "done"
      ? "환경 기준을 저장했어요"
      : stage === "scan"
        ? "정면을 그대로 봐 주세요"
        : "얼굴을 원 안에 맞춰 주세요";
  const sub =
    stage === "done"
      ? "정면 1장을 이번 메이크업의 조명·색온도 기준으로 저장했어요"
      : stage === "scan"
        ? "정면 얼굴을 찍고 조명·색온도를 확인하고 있어요"
        : passed
          ? "필수 조건 4가지를 통과했어요 · 맨얼굴은 권장이에요"
          : "";
  const cta =
    stage === "ready"
      ? passed
        ? "곧 촬영을 시작해요"
        : `조건 맞추는 중 · ${ok} / 4`
      : stage === "scan"
        ? `인식 중… ${scan}%`
        : replay
          ? "등록 완료 · 파우치 확인"
          : "등록 완료 · 분석 계속 보기";

  return (
    <div
      className="absolute inset-0 z-[4] flex animate-fade items-center justify-center bg-[rgba(26,8,18,.62)] p-8"
      role="dialog"
      aria-modal="true"
      aria-label="얼굴 등록"
    >
      {step === "intro" ? (
        <div className="flex w-full flex-col overflow-hidden rounded-[32px] bg-white shadow-[0_30px_80px_rgba(26,8,18,.35)]">
          <ProgressBar pct={pct} text={barText} />
          <div className="grid grid-cols-[minmax(0,.85fr)_minmax(0,1fr)] items-stretch gap-9 p-7">
            <div className="relative min-h-[440px] overflow-hidden rounded-3xl bg-cream">
              {/* eslint-disable-next-line @next/next/no-img-element -- 안내용 샘플 이미지 */}
              <img
                src="/images/sample-face-bare.png"
                alt=""
                className="absolute top-0 -left-[44%] w-[200%] max-w-none"
                style={{ marginTop: "-62%" }}
              />
              <span className="absolute top-1/2 left-1/2 aspect-[3/4] w-[66%] -translate-x-1/2 -translate-y-1/2 rounded-full border-[2.5px] border-dashed border-white/95" />
              <span className="absolute bottom-4 left-4 flex h-[34px] items-center rounded-full bg-white px-3.5 font-label text-[13px] font-bold tracking-[.14em] text-ink">
                FACE ID
              </span>
            </div>
            <div className="flex min-w-0 flex-col justify-center gap-7 py-2 pr-2">
              <h2 className="font-display text-[28px] leading-[1.35] whitespace-nowrap text-ink">
                {replay ? "시작하기 전에" : "기다리는 동안"}
                <br />
                {replay ? "내 얼굴을 확인할게요" : "내 얼굴을 등록해 둘까요?"}
              </h2>
              <div className="flex flex-col gap-[18px]">
                {TIPS.map((t, i) => (
                  <div key={t} className="flex items-center gap-4">
                    <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-pink-pale font-serif text-[24px] text-plum">
                      {i + 1}
                    </span>
                    <span className="text-[20px] font-bold text-ink">{t}</span>
                  </div>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={start}
                  className="flex h-20 items-center justify-between gap-4 rounded-full bg-pink py-0 pr-2.5 pl-8 text-white shadow-[0_14px_30px_rgba(219,19,116,.26)] active:scale-[.98]"
                >
                  <span className="flex items-baseline gap-2.5 whitespace-nowrap">
                    <span className="text-[23px] font-bold">얼굴 등록 시작</span>
                    <span className="text-[17px] font-semibold text-[#FFD9EA]">약 10초</span>
                  </span>
                  <span className="flex size-[60px] shrink-0 items-center justify-center rounded-full bg-white text-pink">
                    <ArrowRight className="size-7" strokeWidth={2.4} aria-hidden />
                  </span>
                </button>
                <button
                  type="button"
                  onClick={onLater}
                  className="text-[17px] font-semibold text-mute underline"
                >
                  나중에
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div
          className="relative flex w-full flex-col items-center gap-[18px] overflow-hidden rounded-[36px] bg-white px-9 pt-6 pb-8 shadow-[0_40px_100px_rgba(26,8,18,.5)]"
          style={{ animation: "mr-rise 320ms cubic-bezier(.2,.8,.2,1) both" }}
        >
          <div className="flex w-full items-center justify-between gap-3">
            <span className="font-label text-[13px] font-bold tracking-[.16em] text-plum">
              FACE ID
            </span>
            <span className="flex h-8 items-center gap-2 rounded-full bg-cream px-3 text-[14px] font-semibold text-ink tabular">
              <span className="size-1.5 rounded-full bg-pink" />
              분석 {pct}%
            </span>
          </div>

          <FaceRing
            stage={stage}
            pct={scan}
            alert={
              stage === "ready"
                ? {
                    ok: passed,
                    text: passed
                      ? "조건 통과 · 메이크업이 감지됐지만 그대로 촬영해요"
                      : CONDITIONS[ok][1],
                  }
                : null
            }
          />

          <div className="flex flex-col items-center gap-2 text-center">
            <span className="font-display text-[30px] leading-[1.3] text-ink">{title}</span>
            <span className="min-h-[27px] text-[18px] leading-[1.5] text-mute">{sub}</span>
            {stage === "ready" && (
              <span className="text-[15px] leading-[1.5] text-plum">
                정면 1장을 찍어 조명·색온도 기준으로 써요 · 이번 메이크업에만 사용해요
              </span>
            )}
          </div>

          <div className="flex flex-wrap justify-center gap-2">
            {stage === "ready" ? (
              CONDITIONS.map(([label], i) => {
                const rec = i === 4;
                const on = !rec && i < ok;
                return (
                  <span
                    key={label}
                    className={cn(
                      "flex h-10 items-center gap-1.5 rounded-full border-[1.5px] px-3.5 text-[16px] font-semibold whitespace-nowrap transition-colors",
                      rec
                        ? "border-dotted border-line-3 bg-white text-mute"
                        : on
                          ? "border-plum bg-plum text-white"
                          : "border-dashed border-line-3 bg-white text-mute",
                    )}
                  >
                    <Check className="size-3.5" strokeWidth={2.6} aria-hidden />
                    {rec ? "맨얼굴 · 권장" : label}
                  </span>
                );
              })
            ) : (
              <span
                className={cn(
                  "flex h-10 items-center gap-1.5 rounded-full px-3.5 text-[16px] font-semibold",
                  scan >= 100 ? "bg-plum text-white" : "bg-cream text-mute",
                )}
              >
                <Check className="size-3.5" strokeWidth={2.6} aria-hidden />
                정면 1장
              </span>
            )}
          </div>

          <div className="mt-1.5 flex w-full gap-3">
            <button
              type="button"
              onClick={stage === "done" ? start : onLater}
              className="flex h-20 shrink-0 items-center rounded-full border-2 border-line px-[30px] text-[21px] font-bold whitespace-nowrap text-ink active:scale-[.97]"
            >
              {stage === "done" ? "다시 촬영" : "나중에"}
            </button>
            <button
              type="button"
              onClick={onDone}
              disabled={stage !== "done"}
              className={cn(
                "flex h-20 min-w-0 flex-1 items-center justify-center gap-3 rounded-full text-[23px] font-bold whitespace-nowrap text-white tabular transition-colors",
                stage === "done" ? "bg-pink" : "bg-line-2",
              )}
            >
              {cta}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/** 모달 상단 분석 진행 바 */
export function ProgressBar({ pct, text }: { pct: number; text: string }) {
  return (
    <div className="relative flex h-[60px] shrink-0 items-center gap-3 bg-cream px-8">
      <span
        className="absolute bottom-0 left-0 h-[3px] bg-pink transition-[width] duration-600 ease-linear"
        style={{ width: `${pct}%` }}
      />
      <span className="size-2 shrink-0 rounded-full bg-pink" />
      <span className="text-[17px] font-semibold text-ink">{text}</span>
      <span className="ml-auto font-serif text-[26px] leading-none text-plum tabular">{pct}%</span>
    </div>
  );
}

const N = 72;
const RING = 540;

/** 눈금 링 + 얼굴 원 */
function FaceRing({
  stage,
  pct,
  alert,
}: {
  stage: Stage;
  pct: number;
  alert: { ok: boolean; text: string } | null;
}) {
  const lit =
    stage === "done"
      ? N
      : stage === "scan"
        ? Math.round(Math.max(0, Math.min(1, pct / 100)) * N)
        : 0;
  return (
    <div className="relative mt-[104px] shrink-0" style={{ width: RING, height: RING }}>
      {Array.from({ length: N }, (_, i) => (
        <span
          key={i}
          className={cn(
            "absolute rounded-full transition-colors duration-150",
            i < lit ? "bg-pink" : "bg-[#E4E0E2]",
          )}
          style={{
            left: RING / 2 - 4.5,
            top: RING / 2 - 262,
            width: 9,
            height: 22,
            transformOrigin: "4.5px 262px",
            transform: `rotate(${(i / N) * 360}deg)`,
          }}
        />
      ))}
      {alert && (
        <div
          key={alert.text}
          className={cn(
            "absolute inset-x-0 -top-[104px] z-[3] mx-auto flex w-max items-center gap-2.5 rounded-full py-4 pr-7 pl-4 text-[21px] font-bold whitespace-nowrap text-white shadow-[0_10px_24px_rgba(58,14,37,.25)]",
            alert.ok ? "bg-plum" : "bg-ink",
          )}
        >
          <span
            className={cn(
              "flex size-9 items-center justify-center rounded-full text-[20px] font-extrabold",
              alert.ok ? "bg-white text-plum" : "bg-lime text-ink",
            )}
          >
            {alert.ok ? <Check className="size-5" strokeWidth={3} aria-hidden /> : "!"}
          </span>
          {alert.text}
        </div>
      )}
      <div className="absolute top-[50px] left-[50px] size-[440px] overflow-hidden rounded-full bg-cream">
        {/* TODO(CAMERA-005): 샘플 얼굴 대신 실시간 카메라 영상 */}
        {/* eslint-disable-next-line @next/next/no-img-element -- 샘플 */}
        <img
          src="/images/sample-face-bare.png"
          alt=""
          className="absolute top-0 -left-[44%] w-[147%] max-w-none"
          style={{ marginTop: "-53%" }}
        />
        {stage === "ready" && (
          <div className="absolute inset-10 rounded-full border-2 border-dashed border-white/90" />
        )}
        {stage === "scan" && (
          <div
            className="absolute inset-x-0 h-0.5 bg-rose shadow-[0_0_12px_2px_rgba(255,143,192,.6)]"
            style={{ top: `${pct}%` }}
          />
        )}
        {stage === "done" && (
          <div className="absolute inset-0 flex animate-fade items-center justify-center bg-[rgba(153,30,90,.55)]">
            <span className="flex size-28 items-center justify-center rounded-full bg-white">
              <Check className="size-[52px] text-plum" strokeWidth={2.6} aria-hidden />
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
