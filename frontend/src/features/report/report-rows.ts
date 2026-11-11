import { stepPhoto, type GuideReport, type StepPhoto } from "@/features/session";

/** 리포트 상세 단계 한 줄. photo가 shot이면 찍은 사진이 shot에 있다 */
export type ReportRow = ReportRowBase & ReportRowPhoto;

/** slot은 찍었지만 사진을 불러오지 못한 자리 */
export type ReportRowPhoto =
  { photo: "none" | "sample" | "bare" | "slot" } | { photo: "shot"; shot: StepPhoto };

interface ReportRowBase {
  no: number;
  title: string;
  guide: string;
  ref: string;
  usedKind: string;
  used: string;
  /** 서버 기록의 단계 사진 주소. 이 기기에 찍은 사진이 없을 때 slot 대신 실제 이미지 */
  photoUrl?: string | null;
}

const PICK_LABEL = {
  picked: { kind: "내가 고른 제품", empty: "" },
  skipped: { kind: "생략", empty: "이 단계는 제품을 쓰지 않았어요" },
  undecided: { kind: "사용 제품", empty: "기록 없음" },
} as const;

/** 단계 사진은 배열 순번이 아니라 stepId로 그 실행(runId)의 사진을 찾는다 */
export function guideReportRows(report: GuideReport, runId?: string): ReportRow[] {
  return report.steps.map((s, i) => {
    const ref = [s.ref?.name, s.ref?.shade].filter(Boolean).join(" ");
    const shot = s.photo ? stepPhoto(runId, s.stepId) : null;
    const used = s.used ? [s.used.brand, s.used.name, s.used.shade].filter(Boolean).join(" ") : "";
    return {
      no: i + 1,
      title: s.title,
      guide: s.summary ?? "영상에서 설명을 찾지 못했어요",
      ref: ref || "영상에서 제품 정보를 찾지 못했어요",
      usedKind: PICK_LABEL[s.pick].kind,
      used: used || PICK_LABEL[s.pick].empty,
      ...(shot ? { photo: "shot" as const, shot } : { photo: s.photo ? "slot" : "none" }),
      photoUrl: s.photoUrl ?? null,
    };
  });
}
