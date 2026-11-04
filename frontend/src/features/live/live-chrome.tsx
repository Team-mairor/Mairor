"use client";

import { ArrowLeft } from "lucide-react";
import type { ReactNode } from "react";

import { useCamera } from "@/features/face";
import { cn } from "@/lib/utils";

import { useFaceState } from "./face-state";
import { useCameraErrorNote, type LiveNoteData } from "./live-state";

/** 좌상단 LIVE 표시 */
export function LiveTag({ className }: { className?: string }) {
  const { status } = useCamera();
  const { face } = useFaceState();
  return (
    <span
      className={cn(
        "flex h-12 items-center gap-2.5 rounded-full border border-white/15 bg-night/80 py-0 pr-[18px] pl-3.5 font-label text-[15px] font-bold tracking-[.14em] text-white",
        className,
      )}
    >
      <span
        className={cn("size-2.5 rounded-full", face ? "bg-mint" : "bg-blush")}
        style={{ animation: "mr-pulse 1.4s ease-out infinite" }}
      />
      {status === "ready" ? "LIVE" : "CAMERA"}
    </span>
  );
}

/** 카메라 오류일 때만 안내 카드를 보여 준다. 인식 알림을 따로 쓰지 않는 화면용 */
export function CameraErrorNote({ className }: { className?: string }) {
  const { face } = useFaceState();
  const note = useCameraErrorNote(face);
  return <LiveNote note={note} className={className} />;
}

/** 상단 안내 카드 (카메라 오류·인식 알림) */
export function LiveNote({ note, className }: { note: LiveNoteData | null; className?: string }) {
  if (!note) return null;
  return (
    <div
      role="status"
      className={cn(
        "absolute inset-x-5 top-[84px] z-[2] flex animate-fade items-center gap-[18px] rounded-3xl border border-white/15 bg-night/90 px-[22px] py-[18px] text-white",
        className,
      )}
    >
      <span className="size-3 shrink-0 rounded-full bg-blush" />
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <span className="text-[22px] leading-[1.3] font-bold text-pretty">{note.title}</span>
        <span className="text-[17px] leading-[1.5] text-pretty text-line-2">{note.desc}</span>
      </div>
      {note.retry && (
        <button
          type="button"
          onClick={note.onRetry}
          className="flex h-[52px] shrink-0 items-center rounded-full bg-white px-[22px] text-[17px] font-bold whitespace-nowrap text-ink active:scale-[.97]"
        >
          {note.retry}
        </button>
      )}
    </div>
  );
}

/** 하단 반투명 패널 */
export function GlassPanel({
  children,
  className,
  coversFace = true,
}: {
  children: ReactNode;
  className?: string;
  /** 패널 뒤 얼굴 부위를 화면 밖으로 판정할지. 화면을 거의 덮는 시트는 false */
  coversFace?: boolean;
}) {
  const { setCoverPanel } = useCamera();
  return (
    <div
      ref={coversFace ? setCoverPanel : undefined}
      className={cn(
        "absolute inset-x-4 bottom-4 flex flex-col gap-5 rounded-[36px] border border-white/10 bg-night/90 px-7 pt-6 pb-[18px] text-white shadow-modal backdrop-blur-2xl",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** 패널 안 동그란 뒤로 버튼 */
export function RoundBack({
  onClick,
  label = "뒤로",
  className,
}: {
  onClick: () => void;
  label?: string;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className={cn(
        "flex size-[72px] shrink-0 items-center justify-center rounded-full border border-white/15 bg-white/8 text-white hover:bg-white/15 active:scale-[.95]",
        className,
      )}
    >
      <ArrowLeft className="size-[26px]" strokeWidth={2.2} aria-hidden />
    </button>
  );
}
