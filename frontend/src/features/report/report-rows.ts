import { groupSteps, type MatchCategory } from "@/features/guide";
import { stepPhoto, type GuideReport, type StepPhoto } from "@/features/session";

/** 리포트 상세 단계 한 줄. photo가 shot이면 찍은 사진이 shot에 있다 */
export type ReportRow = ReportRowBase & ReportRowPhoto;

/** slot은 찍었지만 사진을 불러오지 못한 자리 */
export type ReportRowPhoto =
  { photo: "none" | "sample" | "bare" | "slot" } | { photo: "shot"; shot: StepPhoto };

interface ReportRowBase {
  no: number;
  title: string;
  /** 단계 사진을 묶는 부위. 모르면 단계마다 따로 본다 */
  category: MatchCategory | null;
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
      category: s.category ?? null,
      guide: s.summary ?? "영상에서 설명을 찾지 못했어요",
      ref: ref || "영상에서 제품 정보를 찾지 못했어요",
      usedKind: PICK_LABEL[s.pick].kind,
      used: used || PICK_LABEL[s.pick].empty,
      ...(shot ? { photo: "shot" as const, shot } : { photo: s.photo ? "slot" : "none" }),
      photoUrl: s.photoUrl ?? null,
    };
  });
}

/** 리포트의 단계 사진 칸 하나. 보통은 연속한 같은 부위 단계 묶음이다 */
export interface CaptureTile {
  /** 사진을 보여 줄 단계의 번호. 아래 단계 목록 번호와 같다 */
  no: number;
  label: string;
  /** 사진을 보여 줄 단계. 묶음에서 사진을 남긴 마지막 단계, 없으면 마지막 단계 */
  row: ReportRow;
}

const taken = (r: ReportRow) => r.photo === "shot" || r.photo === "slot";

/**
 * 단계 사진은 묶음마다 한 장이라 묶음 단위로 보여 준다.
 * 찍은 사진이 여러 장인 묶음은 단계마다 찍던 이전 기록이라 사진마다 한 칸으로 나눈다
 * 원하는 단계만 골라 할 수 있어, 사진을 찍지 않은 칸(none)은 보여 주지 않는다
 */
export function captureTiles(rows: readonly ReportRow[]): CaptureTile[] {
  return groupSteps(rows)
    .flatMap((g) => {
      const inGroup = rows.slice(g.start, g.end);
      const shots = inGroup.filter(taken);
      if (shots.length > 1) return shots.map((r) => ({ label: r.title, row: r }));
      const last = [...inGroup].reverse();
      return [{ label: g.label, row: shots[0] ?? last.find((r) => r.photo !== "none") ?? last[0] }];
    })
    .filter((t) => t.row.photo !== "none")
    .map((t) => ({ no: t.row.no, ...t }));
}
