// 단계·제품·리포트를 화면끼리 주고받는 모양. API가 붙으면 lib/api/types와 맞춘다
import type { Makeup, MatchCategory } from "@/features/guide";
import type { PouchCat } from "@/features/pouch";

import type { ReportStep } from "./matching";

/** 영상 속 제품 인식 상태. 확정 제품은 라벨 없음 */
export type RefState = "guess" | "desc" | "unreg";

export interface RefProduct {
  id: string;
  /** 단계 부위 이름 (파운데이션·크림 블러셔·…) */
  cat: string;
  /** 대체 후보를 찾을 파우치 카테고리 (API의 matchCategory) */
  matchCat: PouchCat;
  brand: string;
  name: string;
  color: string;
  /** 호수·컬러명. 영상에서 확인하지 못했으면 null */
  shade: string | null;
  /** 샘플: 내 파우치에 같은 제품이 있는지 */
  have: boolean;
  /** 영상 구간 */
  time: string;
  /** 샘플: 색이 가까운 대체 제품 */
  sub?: { brand: string; name: string; color: string } | null;
  refState?: RefState;
}

export const REF_STATE_LABEL: Record<RefState, string> = {
  guess: "추정",
  desc: "설명란에만 있음",
  unreg: "이름만 확인",
};

/** 단계 안의 동작 하나와 그 팁·주의 */
export interface GuideAction {
  text: string;
  tip: { kind: "tip" | "caution"; text: string } | null;
}

export interface GuideStepInfo {
  /** 원본 가이드의 단계 ID. 얼굴 위 가이드 영역도 이 ID로 찾는다 */
  stepId: string;
  makeup: Makeup;
  en: string;
  short: string;
  title: string;
  /** 동작과 그 동작의 팁·주의 */
  acts: GuideAction[];
  /** 끝내는 기준. 영상에서 확인하지 못했으면 null */
  doneWhen: string | null;
  guide: string;
  area: string;
  /** 프로토타입 가이드 영역 (x, y, w, h · 얼굴 기준 %) */
  a: [number, number, number, number];
  /** 레퍼런스 진하기 위치 (0~100) */
  target: number;
}

export interface ReportSummary {
  /** 실제 가이드 기록에만 있다 */
  guideId?: string;
  guideVersion?: number;
  id: string;
  title: string;
  date: string;
  steps: number;
  /** 대체 제품 수 */
  subs: number;
  isNew?: boolean;
  /** 사진 없이 완료 (단계 사진 저장 안 함) */
  noPhoto?: boolean;
  /** 마지막 단계 사진이 있어 최종 사진으로 쓸 수 있음. 샘플은 없으면 있음으로 본다 */
  finalPhoto?: boolean;
  /** 서버 기록의 완성 사진 주소. 있으면 실제 이미지를 보여 준다 */
  photoUrl?: string | null;
  /** 사진을 저장한 단계 번호. 샘플은 없으면 전부 있음으로 본다 */
  captures?: number[];
  /** 만든 실행 id. 단계 사진을 이 id로 찾는다. 샘플 기록은 없고 샘플 사진을 보여 준다 */
  runId?: string;
  /** 출처 영상 id (VideoItem.id) */
  videoId?: string;
  /** 저장 당시 단계별 확정 제품. 샘플은 없으면 현재 파우치로 매칭한다 */
  items?: ReportStep[];
  /** 실제 가이드 기록의 완료 시점 스냅샷. 있으면 리포트는 이것만 읽는다 */
  guide?: GuideReport;
}

export interface GuideReport {
  videoId: string;
  youtubeVideoId: string | null;
  channelTitle: string;
  steps: GuideReportStep[];
}

export interface GuideReportStep {
  stepId: string;
  title: string;
  /** 단계 사진을 묶는 부위. 이전에 저장한 기록에는 없고, 없으면 단계마다 따로 본다 */
  category?: MatchCategory | null;
  summary: string | null;
  /** 영상 제품 이름·호수 그대로 */
  ref: { name: string | null; shade: string | null } | null;
  pick: "picked" | "skipped" | "undecided";
  /** 고른 파우치 제품의 당시 값 */
  used: { brand: string; name: string; shade: string | null } | null;
  /** 단계 사진을 남겼는지 */
  photo: boolean;
  /** 서버 기록의 단계 사진 주소. 있으면 실제 이미지를 보여 준다 */
  photoUrl?: string | null;
}
