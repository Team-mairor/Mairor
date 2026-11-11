import type { GuideReport } from "@/features/session";

/** 리포트 상세 단계 한 줄 */
export interface ReportRow {
  no: number;
  title: string;
  guide: string;
  ref: string;
  usedKind: string;
  used: string;
  /** slot은 사진을 남겼지만 아직 보여 줄 이미지가 없는 자리 */
  photo: "none" | "sample" | "bare" | "slot";
  /** 서버 기록의 단계 사진 주소. 있으면 slot 대신 실제 이미지 */
  photoUrl?: string | null;
}

const PICK_LABEL = {
  picked: { kind: "내가 고른 제품", empty: "" },
  skipped: { kind: "생략", empty: "이 단계는 제품을 쓰지 않았어요" },
  undecided: { kind: "사용 제품", empty: "기록 없음" },
} as const;

export function guideReportRows(report: GuideReport): ReportRow[] {
  return report.steps.map((s, i) => {
    const ref = [s.ref?.name, s.ref?.shade].filter(Boolean).join(" ");
    const used = s.used ? [s.used.brand, s.used.name, s.used.shade].filter(Boolean).join(" ") : "";
    return {
      no: i + 1,
      title: s.title,
      guide: s.summary ?? "영상에서 설명을 찾지 못했어요",
      ref: ref || "영상에서 제품 정보를 찾지 못했어요",
      usedKind: PICK_LABEL[s.pick].kind,
      used: used || PICK_LABEL[s.pick].empty,
      photo: s.photo ? "slot" : "none",
      photoUrl: s.photoUrl ?? null,
    };
  });
}
