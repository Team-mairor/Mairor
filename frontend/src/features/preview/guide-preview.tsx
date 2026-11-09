"use client";

import { useRouter } from "next/navigation";

import { PillButton } from "@/components/ui/pill-button";
import { useGuide, useRunQuery } from "@/features/guide";
import {
  GlassPanel,
  LiveNote,
  LiveTag,
  parseAlert,
  RoundBack,
  useLiveState,
  type LiveReason,
} from "@/features/live";
import { runHref, useSession } from "@/features/session";

import { previewSummary } from "./preview-summary";

/** 그린 것이 없으므로 숨김·색 정확도 대신 할 일만 안내한다. 카메라 상태 안내는 그대로 둔다 */
const PLAIN_DESC: Record<Exclude<LiveReason, "error" | "starting">, string> = {
  lost: "화면 가운데로 돌아와 주세요.",
  turn: "얼굴이 정면으로 보이게 해 주세요.",
  turned: "얼굴이 정면으로 보이게 해 주세요.",
  cover: "얼굴 전체가 보이게 해 주세요.",
  far: "얼굴이 화면에 크게 보이게 해 주세요.",
  light: "처음 등록한 얼굴보다 어두워요. 밝은 곳으로 옮겨 주세요.",
  "out-of-frame": "얼굴 전체가 화면 가운데에 보이게 해 주세요.",
};

/** 실제 가이드 미리보기. 색상 정보가 없어 레이어 없이 대상 단계만 안내한다 */
export function GuidePreview() {
  const router = useRouter();
  const query = useRunQuery();
  const { load } = useGuide();
  const { state } = useSession();
  const live = useLiveState(parseAlert(query?.get("alert")));
  const reason = live.reason;
  const plain = reason && reason !== "error" && reason !== "starting" ? PLAIN_DESC[reason] : null;
  const note = live.note && plain ? { ...live.note, desc: plain } : live.note;
  if (load.status !== "ready") return null;
  const s = previewSummary(load.guide);

  return (
    <main className="relative flex flex-1 flex-col">
      {note?.live && !note.face && (
        <div className="pointer-events-none absolute top-[30%] left-1/2 h-[540px] w-[420px] -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-dashed border-white/55" />
      )}
      <div className="pointer-events-none absolute inset-x-5 top-5 flex items-center justify-between gap-3">
        <LiveTag />
      </div>
      <LiveNote note={note} />

      <GlassPanel>
        <div className="flex items-baseline gap-3.5">
          <span className="shrink-0 font-serif text-[44px] leading-[.9] text-blush italic">
            Preview
          </span>
          <h1 className="font-display text-[30px] leading-[1.15] text-white">미리보기 준비 중</h1>
        </div>
        <p className="-mt-2 text-[18px] leading-[1.5] text-pretty text-line-2">
          이 영상은 아직 색상 정보가 없어 색을 입혀 볼 수 없어요. 색상 정보가 준비되면 내 얼굴에
          입혀 볼 수 있어요.
        </p>
        <div className="flex flex-col gap-1 rounded-[18px] border border-white/8 bg-white/4 px-[18px] py-3.5 text-[18px] leading-[1.5]">
          <span className="font-bold text-white" data-testid="preview-targets">
            {s.targets
              ? `미리보기 대상 ${s.targets} / 전체 ${s.total}단계 · ${s.kinds.join(" · ")}`
              : "미리볼 수 있는 단계가 없어요"}
          </span>
          {s.excluded.length > 0 && (
            <span className="text-line-2">
              색 비교가 어려운 {s.excluded.join(" · ")} 단계는 빠져요
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <RoundBack onClick={() => router.push("/select")} label="영상 목록으로" />
          <PillButton
            size="cta"
            trailing
            onClick={() => router.push(runHref("/check", state.run.guideId))}
            className="min-w-0 flex-1"
          >
            이 가이드로 단계 안내 시작
          </PillButton>
        </div>
      </GlassPanel>
    </main>
  );
}
