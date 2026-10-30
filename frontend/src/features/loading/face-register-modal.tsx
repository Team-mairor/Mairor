"use client";

import { ArrowRight, Check } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useCamera } from "@/features/face";
import { useCameraErrorNote } from "@/features/live/live-chrome";
import { cn } from "@/lib/utils";

import {
  allPassed,
  captureFace,
  CHECKS,
  eyesClosed,
  saveFacePhoto,
  useFaceCheck,
  type CheckName,
} from "./face-register";

/** 필수 촬영 조건의 이름과 맞지 않을 때 안내 */
const CONDITIONS: Record<CheckName, [label: string, hint: string]> = {
  light: ["밝고 고른 조명", "조명이 너무 어둡거나 밝아요"],
  distance: ["원 안 · 적정 거리", "얼굴을 원 안에 맞춰 주세요"],
  front: ["정면", "고개를 정면으로 바로 해 주세요"],
  clear: ["가림 없음", "얼굴이 가려지지 않게 해 주세요"],
};
const TIPS = ["밝고 고른 조명", "정면 · 이마 드러내기", "맨얼굴이면 더 정확해요"];
/** 조건을 이 시간(ms) 동안 유지하면 촬영한다. 한 프레임만 맞았을 때 찍히지 않게 한다 */
const HOLD_MS = 1500;

type Stage = "ready" | "scan" | "done";

/**
 * 얼굴 등록 모달 (CAMERA-005 · VIDEO-004). 안내 → 카메라 → 실시간 조건 체크 → 조건을 유지하면 자동 촬영.
 * 카메라는 (live) 레이아웃의 것을 켜서 쓰고, 등록을 마치면 미리보기에서 그대로 이어 쓴다.
 */
export function FaceRegisterModal({
  runId,
  pct,
  barText,
  replay,
  onDone,
  onLater,
}: {
  /** 등록 사진을 이 실행에만 쓴다 */
  runId: string;
  /** 분석 진행률 (상단 바) */
  pct: number;
  barText: string;
  replay: boolean;
  onDone: () => void;
  onLater: () => void;
}) {
  const camera = useCamera();
  const cameraError = useCameraErrorNote(false);
  const [step, setStep] = useState<"intro" | "cam">("intro");
  const [done, setDone] = useState(false);
  const [scan, setScan] = useState(0);
  /** 마지막 촬영을 다시 하는 이유 */
  const [retake, setRetake] = useState<null | "failed" | "eyes">(null);
  const cameraReady = camera.status === "ready";
  const { check, frame, passedNow } = useFaceCheck(step === "cam" && cameraReady && !done);
  const passed = allPassed(check);
  const ok = CHECKS.filter((name) => check[name]).length;
  // 조건을 모두 만족하는 동안만 촬영을 진행하고, 잠깐 흔들리는 정도를 넘어 깨지면 처음부터 다시 잰다
  const scanning = passed && !done;
  const stage: Stage = done ? "done" : scanning ? "scan" : "ready";
  // 이미 찍었으면 카메라 오류가 나도 완료로 넘어갈 수 있게 오류 안내를 띄우지 않는다
  const errorNote = done ? null : cameraError;

  const start = () => {
    setStep("cam");
    setDone(false);
    setScan(0);
    setRetake(null);
    void camera.start();
  };

  const capturing = useRef(false);
  useEffect(() => {
    if (!scanning) return;
    // 화면의 판정은 잠깐 흔들려도 통과로 두므로, 유지 시간은 실제로 통과한 프레임 동안만 센다
    let held = 0;
    let last = performance.now();
    // 찍는 사이 모달이 닫히거나 조건이 깨지면 결과를 버린다
    let cancelled = false;
    const timer = setInterval(() => {
      const now = performance.now();
      const passing = passedNow();
      if (passing) held += now - last;
      last = now;
      const p = Math.min(100, (held / HOLD_MS) * 100);
      setScan(p);
      const video = camera.videoRef.current;
      if (p < 100 || !passing || capturing.current || !video) return;
      if (eyesClosed(frame.current)) {
        // 눈 감은 사진은 기준으로 쓰지 않고, 조건을 그대로 유지하면 처음부터 다시 재서 찍는다
        setRetake("eyes");
        held = 0;
        return;
      }
      capturing.current = true;
      captureFace(video)
        .then((photo) => {
          if (cancelled) return;
          saveFacePhoto(runId, photo);
          setRetake(null);
          setDone(true);
        })
        .catch((e) => {
          if (cancelled) return;
          console.error(e);
          setRetake("failed");
          // 조건을 그대로 유지하면 처음부터 다시 재서 찍는다
          held = 0;
        })
        .finally(() => {
          capturing.current = false;
        });
    }, 50);
    return () => {
      cancelled = true;
      setScan(0);
      clearInterval(timer);
      setRetake(null);
    };
  }, [scanning, camera.videoRef, frame, passedNow, runId]);

  // 얼굴을 못 찾았으면 다른 조건은 볼 수 없으니 원에 맞추라는 안내부터 한다
  const firstFailed = ok === 0 ? "distance" : CHECKS.find((name) => !check[name]);
  const title =
    stage === "done"
      ? "환경 기준을 저장했어요"
      : errorNote
        ? errorNote.title
        : !cameraReady
          ? "카메라를 켜는 중이에요"
          : stage === "scan"
            ? "눈을 뜨고 정면을 또렷하게 봐 주세요"
            : "얼굴을 원 안에 맞춰 주세요";
  const sub = errorNote
    ? errorNote.desc
    : retake === "eyes"
      ? "눈을 감은 것 같아요. 눈을 뜨고 그대로 있으면 다시 찍어요"
      : retake === "failed"
        ? "사진을 찍지 못했어요. 그대로 있으면 다시 찍어요"
        : stage === "done"
          ? "정면 1장을 이번 메이크업의 조명·색온도 기준으로 저장했어요"
          : stage === "scan"
            ? "정면 얼굴을 찍고 조명·색온도를 확인하고 있어요"
            : passed
              ? "필수 조건 4가지를 통과했어요 · 맨얼굴은 권장이에요"
              : "";
  const cta =
    stage === "ready"
      ? `조건 맞추는 중 · ${ok} / ${CHECKS.length}`
      : stage === "scan"
        ? `인식 중… ${Math.round(scan)}%`
        : replay
          ? "등록 완료 · 파우치 확인"
          : "등록 완료 · 분석 계속 보기";
  const alert =
    errorNote || !cameraReady || stage !== "ready"
      ? null
      : passed
        ? { ok: true, text: "조건 통과 · 그대로 봐 주세요" }
        : { ok: false, text: CONDITIONS[firstFailed ?? "distance"][1] };

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

          <FaceRing stage={stage} pct={scan} live={cameraReady} alert={alert} />

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
              <>
                {CHECKS.map((name) => (
                  <span
                    key={name}
                    className={cn(
                      "flex h-10 items-center gap-1.5 rounded-full border-[1.5px] px-3.5 text-[16px] font-semibold whitespace-nowrap transition-colors",
                      check[name]
                        ? "border-plum bg-plum text-white"
                        : "border-dashed border-line-3 bg-white text-mute",
                    )}
                  >
                    <Check className="size-3.5" strokeWidth={2.6} aria-hidden />
                    {CONDITIONS[name][0]}
                  </span>
                ))}
                <span className="flex h-10 items-center gap-1.5 rounded-full border-[1.5px] border-dotted border-line-3 bg-white px-3.5 text-[16px] font-semibold whitespace-nowrap text-mute">
                  <Check className="size-3.5" strokeWidth={2.6} aria-hidden />
                  맨얼굴 · 권장
                </span>
              </>
            ) : (
              <span
                className={cn(
                  "flex h-10 items-center gap-1.5 rounded-full px-3.5 text-[16px] font-semibold",
                  stage === "done" ? "bg-plum text-white" : "bg-cream text-mute",
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
            {errorNote ? (
              <button
                type="button"
                onClick={errorNote.onRetry}
                disabled={!errorNote.onRetry}
                className={cn(
                  "flex h-20 min-w-0 flex-1 items-center justify-center gap-3 rounded-full text-[23px] font-bold whitespace-nowrap text-white transition-colors",
                  errorNote.onRetry ? "bg-pink" : "bg-line-2",
                )}
              >
                {errorNote.retry ?? "다시 시도할 수 없어요"}
              </button>
            ) : (
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
            )}
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
  live,
  alert,
}: {
  stage: Stage;
  pct: number;
  /** 카메라가 켜져 영상을 보여 줄 수 있음 */
  live: boolean;
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
        {live && <FaceVideo />}
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

/** 카메라 영상 가운데 정사각형을 거울처럼 뒤집어 원 안에 그린다 */
function FaceVideo() {
  const { videoRef } = useCamera();
  const ref = useRef<HTMLVideoElement>(null);
  // 같은 카메라 스트림을 한 번 더 붙여, 자르기와 좌우 반전은 CSS로 한다. 프레임마다 JS로 그리지 않는다
  useEffect(() => {
    const video = ref.current;
    if (!video) return;
    video.srcObject = videoRef.current?.srcObject ?? null;
    // 화면이 꺼지거나 백그라운드로 가면 브라우저가 멈추고, 돌아와도 다시 재생하지 않는다
    const play = () => {
      if (!video.paused || document.visibilityState !== "visible") return;
      video.play().catch((e) => console.warn("원 안 영상을 재생하지 못했습니다", e));
    };
    play();
    document.addEventListener("visibilitychange", play);
    video.addEventListener("pause", play);
    return () => {
      document.removeEventListener("visibilitychange", play);
      video.removeEventListener("pause", play);
      video.srcObject = null;
    };
  }, [videoRef]);
  return (
    <video
      ref={ref}
      className="absolute inset-0 size-full -scale-x-100 object-cover"
      playsInline
      muted
    />
  );
}
