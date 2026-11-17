// 개발·테스트용 샘플 데이터. 제품 사용자의 파우치·리포트 기록을 대신하는 데 쓰지 않는다.

import type { PouchCat } from "@/domain/pouch";
import type { GuideStepInfo, RefProduct, RefState } from "@/domain/session";
import type { Chapter, VideoItem, VideoState } from "@/domain/video";
import type { Makeup } from "@/vision/guide";

import { MOCK_GUIDE_STEPS, type MockGuideStep } from "./mock-guide";

/** 화장 종류별 화면 표시값. 진하기 목표·색은 API가 붙기 전까지 쓰는 샘플 */
const BY_MAKEUP: Record<
  Exclude<Makeup, "other">,
  { en: string; area: string; a: GuideStepInfo["a"]; target: number; color: string }
> = {
  foundation: { en: "BASE", area: "얼굴 전체", a: [50, 55, 86, 80], target: 55, color: "#E9D2C2" },
  eyeshadow: { en: "EYES", area: "눈두덩", a: [74, 39, 24, 8], target: 56, color: "#C99A86" },
  eyeliner: { en: "LINER", area: "눈꼬리", a: [80, 44, 18, 4], target: 58, color: "#4A3228" },
  blush: { en: "BLUSH", area: "광대", a: [86, 59, 20, 14], target: 86, color: "#EF8E8A" },
  lip: { en: "LIPS", area: "입술", a: [50, 88, 34, 9], target: 60, color: "#B5706B" },
  brow: { en: "BROW", area: "눈썹", a: [74, 32, 24, 6], target: 55, color: "#6B4E3D" },
  mascara: { en: "LASH", area: "속눈썹", a: [74, 42, 22, 6], target: 60, color: "#2B2220" },
  contour: { en: "CONTOUR", area: "얼굴 윤곽", a: [80, 70, 30, 20], target: 50, color: "#B88B6E" },
  highlight: { en: "GLOW", area: "콧대", a: [50, 55, 8, 20], target: 50, color: "#F3E3D3" },
};

/** 따라 하는 단계. 가이드 대상이 아닌 단계(EXCLUDED)는 빼고 원본 순서대로 */
const PLAY_STEPS = MOCK_GUIDE_STEPS.filter(
  (s): s is MockGuideStep & { makeup: Exclude<Makeup, "other"> } => s.type === "GUIDE",
);

export const GUIDE_STEPS: GuideStepInfo[] = PLAY_STEPS.map((s) => {
  const m = BY_MAKEUP[s.makeup];
  return {
    stepId: s.stepId,
    makeup: s.makeup,
    en: m.en,
    short: s.part,
    title: s.part,
    acts: s.actions,
    doneWhen: s.doneWhen,
    guide: s.actions.map((x) => x.text).join(" "),
    area: m.area,
    a: m.a,
    target: m.target,
  };
});

// 샘플: 파우치에 같은 제품이 있는 단계, 대체 후보가 있는 단계, 인식 상태 라벨
const HAVE = new Set(["s5", "s7", "s18"]);
const SUBS: Record<string, RefProduct["sub"]> = {
  s10: { brand: "에뛰드", name: "Play Color Eyes", color: "#C9A98B" },
  s12: { brand: "페리페라", name: "Ink V Shadow 딥브라운", color: "#6B4E3D" },
  s17: { brand: "롬앤", name: "Juicy Lasting Tint", color: "#B5706B" },
};
const REF_STATE: Record<string, RefState> = { s9: "guess", s13: "unreg", s19: "desc" };

/** 화장 종류 → 파우치 카테고리 */
const MATCH_CAT: Record<Exclude<Makeup, "other">, PouchCat> = {
  foundation: "베이스",
  eyeshadow: "아이",
  eyeliner: "아이",
  mascara: "아이",
  brow: "브로우",
  blush: "치크",
  highlight: "치크",
  contour: "치크",
  lip: "립",
};

const mmss = (sec: number) =>
  `${String(Math.floor(sec / 60)).padStart(2, "0")}:${String(Math.floor(sec % 60)).padStart(2, "0")}`;

/** 단계마다 영상 속 제품. GUIDE_STEPS와 같은 순서 */
export const REF_PRODUCTS: RefProduct[] = PLAY_STEPS.map((s) => ({
  id: `r-${s.stepId}`,
  cat: s.part,
  matchCat: MATCH_CAT[s.makeup],
  brand: s.product?.brand ?? "",
  // 파우치는 이름과 호수를 따로 두고 이름으로 같은 제품을 찾으므로 호수는 붙이지 않는다
  name: s.product?.name ?? "",
  color: BY_MAKEUP[s.makeup].color,
  shade: s.product?.shade ?? null,
  have: HAVE.has(s.stepId),
  time: mmss(s.videoRange.startSeconds),
  sub: SUBS[s.stepId] ?? null,
  refState: REF_STATE[s.stepId],
}));

/** 입혀보기 대상 단계(색 있는 단계)의 GUIDE_STEPS 순번. 베이스는 제외 */
const TRY_MAKEUPS: Makeup[] = ["eyeshadow", "eyeliner", "blush", "highlight", "lip"];
export const TRY_STEPS: number[] = GUIDE_STEPS.flatMap((s, i) =>
  TRY_MAKEUPS.includes(s.makeup) ? [i] : [],
);

export const VIDEOS: VideoItem[] = [
  {
    id: "y1",
    ytid: "sWQ8tCgvs0E",
    title: "피부 좋아 보인다는 말 듣는 데일리 메이크업",
    ch: "뷰티 크리에이터 A",
    meta: "조회수 18만회 · 2주 전",
    dur: "12:40",
  },
  {
    id: "y2",
    ytid: "3gPaqVnkTMs",
    title: "쿨톤의 물먹 코랄 봄 메이크업",
    ch: "뷰티 크리에이터 B",
    meta: "조회수 42만회 · 6개월 전",
    dur: "18:05",
  },
  {
    id: "y3",
    ytid: "UNv-fUnGcKM",
    title: "심플하고 세련된 10분 데일리 메이크업",
    ch: "뷰티 크리에이터 C",
    meta: "조회수 9.1만회 · 1개월 전",
    dur: "10:31",
  },
  {
    id: "y4",
    ytid: "VxAXD6PP76I",
    title: "완성도 up! 요즘 진짜 예뻐진 메이크업 · 사람들 잘 모르는 스킬 총집합",
    ch: "뷰티 크리에이터 D",
    meta: "조회수 125만회 · 9개월 전",
    dur: "30:58",
  },
  {
    id: "y5",
    ytid: "eoNi1sl-5RQ",
    title: "봄웜라이트 인생 블러셔 추천",
    ch: "뷰티 크리에이터 E",
    meta: "조회수 63만회 · 8개월 전",
    dur: "16:12",
  },
  {
    id: "y6",
    ytid: "nkuHyldBZS4",
    title: "헬시 코랄 팔레트 메이크업 리뷰",
    ch: "뷰티 크리에이터 F",
    meta: "조회수 15만회 · 1년 전",
    dur: "11:03",
  },
];

/** 영상 챕터. 가이드 대상이 아닌 단계(스킨케어 등 EXCLUDED)는 빼고 따라 하는 단계만 보여 준다 */
export const CHAPTERS: Chapter[] = PLAY_STEPS.map((s) => ({
  time: mmss(s.videoRange.startSeconds),
  label: s.part,
}));

/** 영상 상태 샘플. y2 가이드 있음 · y3 분석 중 · y5 재생 불가 · y6 일일 한도 */
export function videoState(v: VideoItem | null): VideoState {
  if (!v) return "new";
  return (
    ({ y2: "guide", y3: "running", y5: "blocked", y6: "quota" } as Record<string, VideoState>)[
      v.id
    ] ?? "new"
  );
}
