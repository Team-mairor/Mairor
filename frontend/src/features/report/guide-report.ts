import { pickOf } from "@/features/check";
import type { GuideModel } from "@/features/guide";
import type { PouchItem } from "@/features/pouch";
import type { GuideReport, ReportSummary, RunState } from "@/features/session";

/** 남긴 단계 사진을 리포트에 보여 줄지. 촬영·기록과는 따로 끈다 */
export const SHOW_STEP_PHOTOS = true;

type RunSnapshot = Pick<RunState, "choice" | "captures" | "photoOk">;

/** 완료 시점의 단계·선택·촬영을 복사한다. 이후 파우치·가이드가 바뀌어도 그대로다 */
export function buildGuideReport(
  guide: GuideModel,
  run: RunSnapshot,
  pouch: PouchItem[],
): GuideReport {
  return {
    videoId: guide.videoId,
    youtubeVideoId: guide.youtubeVideoId,
    channelTitle: guide.channelTitle,
    steps: guide.steps.map((s) => {
      const pick = pickOf(s.stepId, run.choice, pouch);
      return {
        stepId: s.stepId,
        title: s.label,
        summary: s.summary ?? s.actions[0]?.text ?? null,
        ref: s.product ? { ...s.product } : null,
        pick: pick.kind,
        used:
          pick.kind === "picked"
            ? { brand: pick.item.brand, name: pick.item.name, shade: pick.item.shade ?? null }
            : null,
        photo: run.photoOk && run.captures.includes(s.stepId),
      };
    }),
  };
}

export function guideReportSummary(
  id: string,
  date: Date,
  guide: GuideModel,
  run: RunSnapshot,
  pouch: PouchItem[],
): ReportSummary {
  const report = buildGuideReport(guide, run, pouch);
  return {
    id,
    guideId: guide.guideId,
    guideVersion: guide.guideVersion,
    title: guide.title,
    date: `${date.getMonth() + 1}월 ${date.getDate()}일`,
    steps: report.steps.length,
    subs: 0,
    isNew: true,
    noPhoto: !run.photoOk,
    finalPhoto: report.steps.at(-1)?.photo ?? false,
    videoId: guide.videoId,
    guide: report,
  };
}

export const pickedCount = (report: GuideReport) =>
  report.steps.filter((s) => s.pick === "picked").length;
