"use client";

import { Camera, Home } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { PillButton } from "@/components/ui/pill-button";
import { useTimeout } from "@/lib/hooks/use-timeout";

export type Save = "saving" | "saved" | "fail";

/**
 * 서버 저장을 흉내 낸다. 진입 때 한 번 저장하고, 실패면 다시 시도할 수 있다.
 * commit이 기록을 남기지 못하면 저장 실패로 본다.
 * ponytail: 서버 완료 기록이 붙으면 같은 실행 id로 재요청해 중복을 막는다.
 */
export function useDoneSave(ready: boolean, failFirst: boolean, commit: () => boolean) {
  const [save, setSave] = useState<Save>("saving");
  const timer = useTimeout();
  const retry = () => {
    setSave("saving");
    timer.set(() => setSave(commit() ? "saved" : "fail"), 1200);
  };
  useEffect(() => {
    if (!ready) return;
    timer.set(() => setSave(!failFirst && commit() ? "saved" : "fail"), 1200);
    return timer.clear;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 진입 때 한 번만 저장한다
  }, [ready]);
  return { save, retry };
}

interface DoneViewProps {
  total: number;
  title: string;
  channel: string;
  hasFinal: boolean;
  hasPhoto: boolean;
  /** 마지막 단계 사진 자리 */
  finalPhoto: ReactNode;
  save: Save;
  onRetry: () => void;
  onHome: () => void;
  onReport: () => void;
}

/** 11 완성 화면. 기록 저장 → 리포트 보기 */
export function DoneView({
  total,
  title,
  channel,
  hasFinal,
  hasPhoto,
  finalPhoto,
  save,
  onRetry,
  onHome,
  onReport,
}: DoneViewProps) {
  return (
    <main className="flex min-h-(--screen-h) flex-1 flex-col gap-6 bg-white px-10 pt-9 pb-8 text-ink">
      <div className="flex flex-col gap-3">
        <span className="font-label text-[16px] font-semibold tracking-[.16em] text-navy">
          LOOK COMPLETE · {total} / {total}
        </span>
        <span className="font-serif text-[88px] leading-[.9] text-navy italic">
          Beautifully done.
        </span>
        <h1 className="font-display text-[26px] leading-[1.35] text-pretty">
          {title} · 완성했어요
        </h1>
      </div>

      <div className="relative min-h-0 flex-1 overflow-hidden rounded-3xl border border-line">
        {hasFinal ? (
          <>
            {finalPhoto}
            <span className="absolute top-[18px] left-[18px] rounded-full bg-white px-[18px] py-2.5 font-label text-[15px] font-semibold tracking-[.14em]">
              FINAL · 마지막 단계 사진
            </span>
          </>
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-cream p-6 text-center">
            <span className="flex size-[72px] items-center justify-center rounded-full border-[2.5px] border-dashed border-ash text-navy">
              <Camera className="size-[30px]" strokeWidth={1.8} aria-hidden />
            </span>
            <span className="font-display text-[26px]">미촬영</span>
            <span className="text-[18px] text-mute">
              {hasPhoto
                ? "마지막 단계 사진이 없어요. 찍은 단계 사진은 리포트에 남아요."
                : "사진 없이 완료했어요. 사용한 제품은 리포트에 남아요."}
            </span>
          </div>
        )}
      </div>

      {save === "saving" && (
        <div className="flex items-center gap-3 rounded-[18px] bg-cream px-5 py-4" role="status">
          <span
            className="size-2.5 shrink-0 rounded-full bg-cyan"
            style={{ animation: "mr-pulse 1.4s ease-out infinite" }}
          />
          <span className="text-[19px] font-semibold">기록 저장 중…</span>
        </div>
      )}
      {save === "fail" && (
        <div
          className="flex items-center gap-4 rounded-[18px] border-[1.5px] border-cyan bg-ice-pale py-4 pr-4 pl-5"
          role="alert"
        >
          <span className="flex min-w-0 flex-1 flex-col gap-1">
            <span className="text-[19px] font-bold text-navy">기록을 저장하지 못했어요</span>
            <span className="text-[16px] text-mute">다시 시도해도 같은 기록으로 저장돼요.</span>
          </span>
          <button
            type="button"
            onClick={onRetry}
            className="flex h-14 shrink-0 items-center rounded-full bg-ice px-6 text-[18px] font-bold whitespace-nowrap text-ink"
          >
            다시 시도
          </button>
        </div>
      )}
      {save === "saved" && (
        <div className="flex items-center gap-3 rounded-[18px] bg-cream px-5 py-4" role="status">
          <span className="size-2.5 shrink-0 rounded-full bg-navy" />
          <span className="min-w-0 flex-1 text-[19px] font-semibold">기록을 저장했어요</span>
        </div>
      )}

      <div className="flex min-w-0 flex-col gap-1.5 px-1">
        <span className="font-label text-[15px] font-semibold tracking-[.14em] text-navy">
          출처
        </span>
        <span className="font-display text-[30px] leading-[1.25] text-pretty">{title}</span>
        <span className="text-[19px] font-semibold text-mute">{channel}</span>
      </div>

      <div className="-mx-10 -mb-8 flex items-center gap-3 border-t border-line px-10 pt-5 pb-7">
        <button
          type="button"
          onClick={onHome}
          aria-label="홈"
          className="flex size-20 shrink-0 items-center justify-center rounded-full border-2 border-line hover:bg-cream-2 active:scale-[.95]"
        >
          <Home className="size-7" strokeWidth={2} aria-hidden />
        </button>
        <PillButton
          size="hero"
          trailing
          onClick={() => save === "saved" && onReport()}
          disabled={save !== "saved"}
          className="min-w-0 flex-1 transition-opacity disabled:bg-ice disabled:opacity-45"
        >
          <span className="flex flex-col gap-0.5">
            <span className="whitespace-nowrap">리포트 보기</span>
            <span className="truncate text-[15px] font-medium text-navy">
              {hasPhoto ? "스텝별 사진 · 사용한 제품" : "사용한 제품 · 사진 없음"}
            </span>
          </span>
        </PillButton>
      </div>
    </main>
  );
}

/** 실제 사진 연결 전까지 쓰는 사진 자리 */
export function PhotoSlot({ label }: { label: string }) {
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-cream-2 p-6 text-center">
      <Camera className="size-[30px] text-navy" strokeWidth={1.8} aria-hidden />
      <span className="text-[18px] font-semibold text-ink">{label}</span>
    </div>
  );
}
