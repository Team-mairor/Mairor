"use client";

import { ArrowRight, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  GlassPanel,
  LiveNote,
  LiveTag,
  RoundBack,
  parseAlert,
  useLiveState,
} from "@/features/live/live-chrome";
import { MakeupOverlay } from "@/features/overlay";
import { REF_PRODUCTS, TRY_STEPS } from "@/lib/mock-data";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";

// 레시피 연동 전까지는 ?layers=경로 로 레이어 파일을 바꿔 본다.
const DEFAULT_LAYERS = "/fixtures/layers/sample.json";
const PARTS = TRY_STEPS.map((i) => REF_PRODUCTS[i]);

/** 07 미리보기 · 실시간 입혀보기 (PREVIEW-001 · CAMERA-001 · CAMERA-004). ?alert=lost|turn|cover|far|light 는 알림 확인용 */
export default function PreviewPage() {
  const router = useRouter();
  const query = useQuery();
  const [bare, setBare] = useState(false);
  // 진입 직후 2.7초 동안 안내 토스트 (프로토타입의 반짝임 연출을 토스트로 줄임)
  const [intro, setIntro] = useState(true);
  useEffect(() => {
    const t = setTimeout(() => setIntro(false), 2700);
    return () => clearTimeout(t);
  }, []);
  const alert = parseAlert(query?.get("alert"));
  const { note, canRender } = useLiveState(alert);
  const layersUrl = query ? (query.get("layers") ?? DEFAULT_LAYERS) : null;
  // 알림·카메라 오류·얼굴 없음이면 메이크업을 숨긴다 (CAMERA-004)
  const hide = bare || !canRender;

  return (
    <main className="relative flex flex-1 flex-col">
      <MakeupOverlay layersUrl={layersUrl} hidden={hide} />
      {note?.live && !note.face && (
        <div className="pointer-events-none absolute top-[30%] left-1/2 h-[540px] w-[420px] -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-dashed border-white/55" />
      )}

      <div className="pointer-events-none absolute inset-x-5 top-5 flex items-center justify-between gap-3">
        <LiveTag />
      </div>
      <LiveNote note={note} />
      {intro && (
        <div
          className="pointer-events-none absolute inset-x-0 bottom-[calc(16px+100%*0)] z-[2] mx-auto mb-[380px] flex w-max items-center gap-2.5 rounded-full bg-ink py-3 pr-5 pl-3.5 text-[16px] font-bold text-white shadow-[0_10px_24px_rgba(58,14,37,.3)]"
          style={{ animation: "mr-fade 400ms cubic-bezier(.34,1.56,.64,1) both" }}
        >
          <Sparkles className="size-5 text-lime" aria-hidden />
          영상 속 메이크업을 내 얼굴에 입혀 볼게요
        </div>
      )}

      <GlassPanel>
        <div className="flex items-baseline gap-3.5">
          <span className="shrink-0 font-serif text-[44px] leading-[.9] text-rose italic">
            Live
          </span>
          <h1 className="font-display text-[30px] leading-[1.15] text-white">
            내 얼굴에 바로 입혀보는 중
          </h1>
        </div>
        <p className="-mt-2 text-[18px] leading-[1.5] text-pretty text-line-2">
          피부 표현(파운데이션 · 컨실러)은 색 비교가 어려워 빠져요 · {PARTS.length} /{" "}
          {REF_PRODUCTS.length} 단계 미리보기
        </p>
        <div className="-mt-1 grid grid-cols-2 gap-2.5">
          {[
            { off: false, label: "메이크업 입히기" },
            { off: true, label: "민낯으로 보기" },
          ].map((m) => {
            const on = bare === m.off;
            return (
              <button
                key={m.label}
                type="button"
                onClick={() => setBare(m.off)}
                aria-pressed={on}
                className={cn(
                  "flex min-h-16 items-center justify-center gap-3 rounded-[18px] border px-[18px] transition-colors",
                  on ? "border-rose/60 bg-white/12" : "border-white/8 bg-white/4",
                )}
              >
                {!m.off && (
                  <span className="flex shrink-0 pl-1.5">
                    {PARTS.map((p) => (
                      <span
                        key={p.id}
                        className={cn(
                          "-ml-1.5 size-[22px] rounded-full border-2",
                          on ? "border-white" : "border-white/30",
                        )}
                        style={{ background: p.color }}
                      />
                    ))}
                  </span>
                )}
                <span
                  className={cn(
                    "text-[22px] font-bold whitespace-nowrap",
                    on ? "text-white" : "text-ash",
                  )}
                >
                  {m.label}
                </span>
              </button>
            );
          })}
        </div>
        <div className="flex items-center gap-3">
          <RoundBack onClick={() => router.push("/select")} label="영상 입력으로" />
          <button
            type="button"
            onClick={() => router.push("/check")}
            className="flex h-[72px] min-w-0 flex-1 items-center justify-between gap-4 rounded-full bg-pink py-0 pr-2.5 pl-[30px] text-white shadow-[0_12px_28px_rgba(219,19,116,.38)] active:scale-[.98]"
          >
            <span className="truncate text-[22px] font-bold">이 메이크업으로 시작하기</span>
            <span className="flex size-[54px] shrink-0 items-center justify-center rounded-full bg-white text-pink">
              <ArrowRight className="size-[26px]" strokeWidth={2.4} aria-hidden />
            </span>
          </button>
        </div>
      </GlassPanel>
    </main>
  );
}
