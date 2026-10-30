// 프로토타입 v11의 샘플 데이터. API 연동 전까지 화면을 채우는 용도이며 서버 응답 규격이 아니다.
// ponytail: 하드코딩 샘플. API 클라이언트가 붙으면 이 파일을 지우고 타입만 lib/api/types로 옮긴다.

import type { Makeup } from "@/features/guide";

import { MOCK_GUIDE_STEPS, type MockGuideStep } from "./mock-guide";

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

export interface GuideStepInfo {
  /** 원본 가이드의 단계 ID. 얼굴 위 가이드 영역도 이 ID로 찾는다 */
  stepId: string;
  makeup: Makeup;
  en: string;
  short: string;
  title: string;
  acts: string[];
  guide: string;
  area: string;
  /** 프로토타입 가이드 영역 (x, y, w, h · 얼굴 기준 %) */
  a: [number, number, number, number];
  /** 레퍼런스 진하기 위치 (0~100) */
  target: number;
}

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
    acts: s.actions.map((x) => x.text),
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
  have: HAVE.has(s.stepId),
  time: mmss(s.videoRange.startSeconds),
  sub: SUBS[s.stepId] ?? null,
  refState: REF_STATE[s.stepId],
}));

/** 미리보기·입혀보기 대상 단계(색 있는 단계)의 GUIDE_STEPS 순번. 베이스는 제외 */
const TRY_MAKEUPS: Makeup[] = ["eyeshadow", "eyeliner", "blush", "highlight", "lip"];
export const TRY_STEPS: number[] = GUIDE_STEPS.flatMap((s, i) =>
  TRY_MAKEUPS.includes(s.makeup) ? [i] : [],
);

export interface VideoItem {
  id: string;
  ytid: string;
  title: string;
  ch: string;
  meta: string;
  dur: string;
}

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
    ytid: "B4W4ueREbs0",
    title: "코랄로 해본 공주 메이크업",
    ch: "뷰티 크리에이터 D",
    meta: "조회수 27만회 · 7개월 전",
    dur: "14:48",
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

/** 영상 상태 (API-VIDEO-001 응답을 흉내 낸 샘플 분기) */
export type VideoState = "new" | "guide" | "running" | "blocked" | "quota";

export function videoThumb(ytid: string) {
  return `https://i.ytimg.com/vi/${ytid}/hqdefault.jpg`;
}

export interface Chapter {
  time: string;
  label: string;
}

/** 영상 챕터. 가이드 대상이 아닌 단계(스킨케어 등 EXCLUDED)는 빼고 따라 하는 단계만 보여 준다 */
export const CHAPTERS: Chapter[] = PLAY_STEPS.map((s) => ({
  time: mmss(s.videoRange.startSeconds),
  label: s.part,
}));

export const POUCH_CATS = [
  "베이스",
  "아이",
  "브로우",
  "치크",
  "립",
  "스킨케어",
  "네일",
  "향수",
  "도구",
] as const;
export type PouchCat = (typeof POUCH_CATS)[number];

/** 대체 후보 매칭 대상 카테고리. 나머지는 파우치 보관만 */
export const MATCH_CATS: PouchCat[] = ["베이스", "아이", "브로우", "치크", "립"];
/** 호수·컬러를 묻지 않는 카테고리 */
export const NO_SHADE_CATS: PouchCat[] = ["스킨케어", "향수", "도구"];

/** 카테고리별 종류 → 일러스트 키 (public/ill/<key>.png) */
export const POUCH_TYPES: Record<PouchCat, [label: string, ill: string][]> = {
  베이스: [
    ["쿠션", "cushion"],
    ["파운데이션", "foundation"],
    ["컨실러", "concealer"],
    ["선크림", "sunscreen"],
    ["파우더", "powder"],
    ["스틱", "stick"],
  ],
  아이: [
    ["섀도우 팔레트", "palette"],
    ["마스카라", "mascara"],
    ["아이라이너", "eyeliner"],
    ["인조 속눈썹", "lashes"],
  ],
  브로우: [["브로우 펜슬", "pencil"]],
  치크: [
    ["블러셔", "blush"],
    ["하이라이터", "highlighter"],
    ["컴팩트", "compact"],
  ],
  립: [
    ["립스틱", "lip"],
    ["립글로스", "gloss"],
    ["립틴트", "tint"],
    ["립밤 · 팟", "balm"],
    ["리퀴드 립", "liquid-lip"],
  ],
  스킨케어: [
    ["토너", "toner"],
    ["세럼 · 앰플", "serum"],
    ["크림", "jar"],
    ["클렌징 폼", "cleansing-foam"],
    ["클렌징 오일", "cleansing-oil"],
    ["핸드 · 아이크림", "cream-tube"],
    ["마스크팩", "sheet-mask"],
    ["미스트", "spray"],
  ],
  네일: [
    ["네일 폴리시", "nail"],
    ["네일 파일", "nail-file"],
  ],
  향수: [["향수", "perfume"]],
  도구: [
    ["브러시", "brush"],
    ["퍼프", "puff"],
    ["스펀지", "sponge"],
    ["뷰러", "curler"],
    ["손거울", "mirror"],
    ["족집게", "tweezers"],
    ["화장솜", "cotton"],
    ["면봉", "swab"],
  ],
};

/** 일러스트 원본 크기 (px). 스티커를 같은 면적으로 맞출 때 쓴다 */
export const ILL_SIZE: Record<string, [number, number]> = {
  gloss: [110, 214],
  tint: [132, 214],
  balm: [174, 156],
  "liquid-lip": [142, 211],
  cushion: [176, 167],
  foundation: [164, 212],
  concealer: [166, 214],
  sunscreen: [148, 212],
  powder: [174, 166],
  puff: [176, 95],
  sponge: [176, 185],
  stick: [130, 212],
  mascara: [176, 198],
  eyeliner: [170, 207],
  palette: [176, 170],
  curler: [176, 148],
  lashes: [176, 156],
  blush: [176, 151],
  highlighter: [176, 151],
  toner: [140, 214],
  serum: [138, 213],
  "cleansing-foam": [148, 212],
  "cleansing-oil": [142, 212],
  "cream-tube": [152, 210],
  "sheet-mask": [174, 199],
  cotton: [174, 112],
  swab: [158, 214],
  nail: [156, 213],
  "nail-file": [174, 181],
  perfume: [174, 194],
  mirror: [174, 208],
  tweezers: [114, 213],
  // 선화 일러스트 (fill·line 두 장)
  lip: [77, 248],
  compact: [136, 206],
  jar: [195, 192],
  spray: [110, 269],
  pencil: [92, 274],
  brush: [144, 339],
};

export const SHADE_COLORS = [
  "#E9D2C2",
  "#EF8E8A",
  "#B5706B",
  "#C9A98B",
  "#6B4E3D",
  "#DB1374",
  "#991E5A",
  "#F3E3D3",
];

export interface PouchItem {
  id: string;
  cat: PouchCat;
  /** 종류 (POUCH_TYPES 라벨). 없으면 카테고리 첫 종류 */
  type?: string;
  brand: string;
  name: string;
  /** 호수·컬러명 */
  shade?: string;
  /** 대표 색. 없으면 대체 후보에서 빠진다 */
  color?: string | null;
}

/** 샘플 파우치. 보유로 보여 줄 단계(HAVE)의 영상 제품과 대체 추천 제품(SUBS)을 넣는다 */
export const DEFAULT_POUCH: PouchItem[] = [
  ...REF_PRODUCTS.filter((r) => r.have).map((r) => ({
    cat: r.matchCat,
    brand: r.brand,
    name: r.name,
    color: r.color,
  })),
  ...REF_PRODUCTS.flatMap((r) => (r.sub ? [{ cat: r.matchCat, ...r.sub }] : [])),
].map((p, i) => ({ id: `p${i + 1}`, ...p }));

/** 샘플 호수 목록 (API-POUCH-001 흉내) */
export const SHADE_OPTIONS: { name: string; color: string }[] = [
  { name: "01 쥬시 코랄", color: "#EF8E8A" },
  { name: "06 피그 피그", color: "#B5706B" },
  { name: "09 로즈 MLBB", color: "#C8235F" },
  { name: "12 피치 글로우", color: "#F2899B" },
];

export interface ReportSummary {
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
  /** 사진을 저장한 단계 번호. 샘플은 없으면 전부 있음으로 본다 */
  captures?: number[];
  /** 출처 영상 id (VideoItem.id) */
  videoId?: string;
  /** 저장 당시 단계별 확정 제품. 샘플은 없으면 현재 파우치로 매칭한다 */
  items?: ReportStepSnapshot[];
}

/** features/session의 ReportStep과 같은 모양. 샘플 데이터가 feature 타입을 역참조하지 않게 여기에 둔다 */
export interface ReportStepSnapshot {
  kind: "same" | "sub" | "none";
  used: { brand: string; name: string } | null;
}

export const DEFAULT_REPORTS: ReportSummary[] = [
  { id: "rp1", title: "면접용 내추럴 룩", date: "10월 16일", steps: 7, subs: 1 },
  { id: "rp2", title: "글로시 립 포인트", date: "10월 12일", steps: 5, subs: 0 },
  { id: "rp3", title: "봄 웜 코랄 데일리", date: "10월 8일", steps: 6, subs: 2 },
  { id: "rp4", title: "음영 섀도 연습", date: "10월 3일", steps: 4, subs: 1 },
];

/** 샘플 계정 (로그인·중복 확인 데모) */
export const EXISTING_EMAILS = ["hello.jooyeon@gmail.com", "member@example.com"];

/** 분석 진행 단계 (API progressStage) */
export const ANALYSIS_PHASES: [en: string, label: string, from: number][] = [
  ["QUEUED", "대기", 0],
  ["FETCH", "영상 불러오기", 3],
  ["SCENES", "구간 나누기", 12],
  ["DETECT", "제품 인식", 28],
  ["STEPS", "단계 추출", 52],
  ["GUIDE", "가이드 구성", 80],
];
