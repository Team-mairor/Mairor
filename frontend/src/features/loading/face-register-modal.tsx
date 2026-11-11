"use client";

import { Check } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Modal } from "@/components/ui/modal";
import { PillButton } from "@/components/ui/pill-button";
import {
  allPassed,
  captureFace,
  CHECKS,
  DISTANCE_HINT_TEXT,
  eyesClosed,
  saveFacePhoto,
  useCamera,
  useFaceCheck,
  type CheckName,
} from "@/features/face";
import { useCameraErrorNote } from "@/features/live";
import { errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

import { FaceDemo } from "./face-demo";
import { FacePosition } from "./face-position";
import { ProgressBar } from "./progress-bar";

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
 * 얼굴 등록 모달. 안내 → 카메라 → 실시간 조건 체크 → 조건을 유지하면 자동 촬영.
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
  /** 실패하면 던진 오류를 창에 보여 준다 */
  onDone: () => Promise<void> | void;
  onLater: () => void;
}) {
  const camera = useCamera();
  const cameraError = useCameraErrorNote(false);
  const [step, setStep] = useState<"intro" | "cam">("intro");
  const [done, setDone] = useState(false);
  const [scan, setScan] = useState(0);
  /** 마지막 촬영을 다시 하는 이유 */
  const [retake, setRetake] = useState<null | "failed" | "eyes">(null);
  /** 등록 완료(onDone)를 기다리는 중 · 실패한 오류 */
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);
  const cameraReady = camera.status === "ready";
  const { check, found, hint, frame, passedNow } = useFaceCheck(
    step === "cam" && cameraReady && !done,
  );
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
    setSaveError(null);
    void camera.start();
  };
  const finish = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      await onDone();
    } catch (e) {
      setSaveError(e);
    } finally {
      setSaving(false);
    }
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
      ? saveError
        ? "얼굴 등록을 저장하지 못했어요"
        : "환경 기준을 저장했어요"
      : errorNote
        ? errorNote.title
        : !cameraReady
          ? "카메라를 켜는 중이에요"
          : stage === "scan"
            ? "눈을 뜨고 정면을 또렷하게 봐 주세요"
            : "얼굴을 원 안에 맞춰 주세요";
  const sub = errorNote
    ? errorNote.desc
    : saveError
      ? `등록을 저장하지 못했어요. ${errorMessage(saveError)}`
      : retake === "eyes"
        ? "눈을 감은 것 같아요. 눈을 뜨고 그대로 있으면 다시 찍어요"
        : retake === "failed"
          ? "사진을 찍지 못했어요. 그대로 있으면 다시 찍어요"
          : stage === "done"
            ? "정면 1장을 이번 메이크업의 조명·색온도 기준으로 저장했어요"
            : stage === "scan"
              ? "정면 얼굴을 찍고 조명·색온도를 확인하고 있어요"
              : passed
                ? "필수 조건 4가지를 통과했어요"
                : found && !check.distance
                  ? "실선 얼굴이 점선 타원을 채우고 원 가운데에 오면 돼요"
                  : "";
  const cta =
    stage === "ready"
      ? `조건 맞추는 중 · ${ok} / ${CHECKS.length}`
      : stage === "scan"
        ? `인식 중… ${Math.round(scan)}%`
        : saving
          ? "등록하는 중"
          : saveError
            ? "다시 등록하기"
            : replay
              ? "등록 완료 · 파우치 확인"
              : "등록 완료 · 분석 계속 보기";
  const alert =
    errorNote || !cameraReady || stage !== "ready"
      ? null
      : passed
        ? { ok: true, text: "조건 통과 · 그대로 봐 주세요" }
        : {
            ok: false,
            // 거리는 '원 안에 맞춰 주세요' 대신 가까이·뒤로·어느 쪽으로 옮길지 알려 준다
            text:
              (firstFailed ?? "distance") === "distance" && hint
                ? DISTANCE_HINT_TEXT[hint]
                : CONDITIONS[firstFailed ?? "distance"][1],
          };

  return (
    <Modal
      open
      label="얼굴 등록"
      overlayClassName="z-[4] animate-fade p-8"
      className={
        step === "intro"
          ? "flex max-w-none animate-none flex-col overflow-hidden rounded-[32px] p-0"
          : "relative flex max-w-none animate-[mr-rise_320ms_cubic-bezier(.2,.8,.2,1)_both] flex-col items-center gap-[18px] overflow-hidden rounded-[36px] px-9 pt-6 pb-8"
      }
    >
      {step === "intro" ? (
        <>
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
                    <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-ice-pale font-serif text-[24px] text-navy">
                      {i + 1}
                    </span>
                    <span className="text-[20px] font-bold text-ink">{t}</span>
                  </div>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <PillButton size="hero" trailing onClick={start}>
                  <span className="flex items-baseline gap-2.5 whitespace-nowrap">
                    <span className="text-[23px] font-bold">얼굴 등록 시작</span>
                    <span className="text-[17px] font-semibold text-navy">약 10초</span>
                  </span>
                </PillButton>
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
        </>
      ) : (
        <>
          <div className="flex w-full items-center justify-between gap-3">
            <span className="font-label text-[13px] font-bold tracking-[.16em] text-navy">
              FACE ID
            </span>
            <span className="flex h-8 items-center gap-2 rounded-full bg-cream px-3 text-[14px] font-semibold text-ink tabular">
              <span className="size-1.5 rounded-full bg-cyan" />
              분석 {pct}%
            </span>
          </div>

          <FaceRing stage={stage} pct={scan} live={cameraReady} face={found} alert={alert} />

          <div className="flex flex-col items-center gap-2 text-center">
            <span className="font-display text-[30px] leading-[1.3] text-ink">{title}</span>
            <span className="min-h-[27px] text-[18px] leading-[1.5] text-mute">{sub}</span>
            {stage === "ready" && (
              <span className="text-[15px] leading-[1.5] text-navy">
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
                        ? "border-navy bg-navy text-white"
                        : "border-dashed border-line-3 bg-white text-mute",
                    )}
                  >
                    <Check className="size-3.5" strokeWidth={2.6} aria-hidden />
                    {CONDITIONS[name][0]}
                  </span>
                ))}
              </>
            ) : (
              <span
                className={cn(
                  "flex h-10 items-center gap-1.5 rounded-full px-3.5 text-[16px] font-semibold",
                  stage === "done" ? "bg-navy text-white" : "bg-cream text-mute",
                )}
              >
                <Check className="size-3.5" strokeWidth={2.6} aria-hidden />
                정면 1장
              </span>
            )}
          </div>

          <div className="mt-1.5 flex w-full gap-3">
            <PillButton
              variant="line"
              size="hero"
              disabled={saving}
              onClick={stage === "done" ? start : onLater}
            >
              {stage === "done" ? "다시 촬영" : "나중에"}
            </PillButton>
            {errorNote ? (
              <PillButton
                size="hero"
                onClick={errorNote.onRetry}
                disabled={!errorNote.onRetry}
                className="min-w-0 flex-1"
              >
                {errorNote.retry ?? "다시 시도할 수 없어요"}
              </PillButton>
            ) : (
              <PillButton
                size="hero"
                onClick={() => void finish()}
                disabled={stage !== "done" || saving}
                className="min-w-0 flex-1"
              >
                {cta}
              </PillButton>
            )}
          </div>
        </>
      )}
    </Modal>
  );
}

const N = 72;
/** 눈금 링 지름. 얼굴 원은 안쪽으로 50px씩 들어간다. 튜토리얼에서 얼굴이 화면을 채우는 거리에 맞춰 크게 둔다 */
const RING = 620;
const FACE = RING - 100;
/** 눈금 하나의 길이와 링 중심에서 눈금 바깥 끝까지 거리 */
const TICK = 22;
const TICK_R = RING / 2 - 8;

/** 눈금 링 + 얼굴 원 */
function FaceRing({
  stage,
  pct,
  live,
  face,
  alert,
}: {
  stage: Stage;
  pct: number;
  /** 카메라가 켜져 영상을 보여 줄 수 있음 */
  live: boolean;
  /** 얼굴이 잡혔음. 안 잡혔으면 원 안에 맞추는 예시를 띄운다 */
  face: boolean;
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
            i < lit ? "bg-cyan" : "bg-line-2",
          )}
          style={{
            left: RING / 2 - 4.5,
            top: RING / 2 - TICK_R,
            width: 9,
            height: TICK,
            transformOrigin: `4.5px ${TICK_R}px`,
            transform: `rotate(${(i / N) * 360}deg)`,
          }}
        />
      ))}
      {alert && (
        <div
          key={alert.text}
          className={cn(
            "absolute inset-x-0 -top-[104px] z-[3] mx-auto flex w-max items-center gap-2.5 rounded-full py-4 pr-7 pl-4 text-[21px] font-bold whitespace-nowrap text-white shadow-float",
            alert.ok ? "bg-navy" : "bg-ink",
          )}
        >
          <span
            className={cn(
              "flex size-9 items-center justify-center rounded-full text-[20px] font-extrabold",
              alert.ok ? "bg-white text-ink" : "bg-mint text-ink",
            )}
          >
            {alert.ok ? <Check className="size-5" strokeWidth={3} aria-hidden /> : "!"}
          </span>
          {alert.text}
        </div>
      )}
      <div
        className="absolute top-[50px] left-[50px] overflow-hidden rounded-full bg-cream"
        style={{ width: FACE, height: FACE }}
      >
        {live && <FaceVideo />}
        {stage === "ready" && !face && <FaceDemo />}
        {/* 촬영하는 동안에도 자리를 지키도록 위치를 계속 보여 준다 */}
        {stage !== "done" && <FacePosition size={FACE} />}
        {stage === "scan" && (
          <div
            className="absolute inset-x-0 h-0.5 bg-blush shadow-[0_0_12px_2px_color-mix(in_srgb,var(--color-blush)_60%,transparent)]"
            style={{ top: `${pct}%` }}
          />
        )}
        {stage === "done" && (
          <div className="absolute inset-0 flex animate-fade items-center justify-center bg-navy/55">
            <span className="flex size-28 items-center justify-center rounded-full bg-white">
              <Check className="size-[52px] text-navy" strokeWidth={2.6} aria-hidden />
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
