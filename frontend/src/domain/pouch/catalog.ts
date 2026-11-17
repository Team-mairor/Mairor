// 파우치 카테고리·일러스트 크기. 화면과 매칭이 함께 쓰는 고정값.
// 카테고리·종류 목록은 서버(GET /v1/product-categories)가 기준이고, 여기에는 화면 표시·그림에 필요한 것만 둔다

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

/** 카테고리 → 서버 코드. 9개 코드는 API 명세 4절의 고정값이다 */
export const CAT_CODE: Record<PouchCat, string> = {
  베이스: "BASE",
  아이: "EYE",
  브로우: "BROW",
  치크: "CHEEK",
  립: "LIP",
  스킨케어: "SKINCARE",
  네일: "NAIL",
  향수: "FRAGRANCE",
  도구: "TOOL",
};

/** 서버 카테고리 코드 → 화면 카테고리. 모르는 코드는 도구로 둔다 */
export function catOf(code: string): PouchCat {
  return POUCH_CATS.find((c) => CAT_CODE[c] === code) ?? "도구";
}

/** 대체 후보 매칭 대상 카테고리. 나머지는 파우치 보관만 */
export const MATCH_CATS: PouchCat[] = ["베이스", "아이", "브로우", "치크", "립"];

/**
 * 종류 코드 → 일러스트 키 (public/ill/<key>.png).
 * 종류 코드는 서버의 임시 제안이라(API-POUCH-008) 여기 없는 코드는 카테고리 기본 그림(CAT_ILL)을 쓴다
 */
export const TYPE_ILL: Record<string, string> = {
  CUSHION: "cushion",
  FOUNDATION: "foundation",
  CONCEALER: "concealer",
  SUNSCREEN: "sunscreen",
  POWDER: "powder",
  BASE_STICK: "stick",
  EYESHADOW_PALETTE: "palette",
  MASCARA: "mascara",
  EYELINER: "eyeliner",
  FALSE_LASHES: "lashes",
  BROW_PENCIL: "pencil",
  BLUSHER: "blush",
  HIGHLIGHTER: "highlighter",
  COMPACT: "compact",
  LIPSTICK: "lip",
  LIP_GLOSS: "gloss",
  LIP_TINT: "tint",
  LIP_BALM: "balm",
  LIQUID_LIP: "liquid-lip",
  TONER: "toner",
  SERUM_AMPOULE: "serum",
  CREAM: "jar",
  CLEANSING_FOAM: "cleansing-foam",
  CLEANSING_OIL: "cleansing-oil",
  HAND_EYE_CREAM: "cream-tube",
  MASK_PACK: "sheet-mask",
  MIST: "spray",
  NAIL_POLISH: "nail",
  NAIL_FILE: "nail-file",
  PERFUME: "perfume",
  BRUSH: "brush",
  PUFF: "puff",
  SPONGE: "sponge",
  EYELASH_CURLER: "curler",
  HAND_MIRROR: "mirror",
  TWEEZERS: "tweezers",
  COTTON_PAD: "cotton",
  COTTON_SWAB: "swab",
};

/** 종류를 모를 때 카테고리 기본 그림 */
export const CAT_ILL: Record<PouchCat, string> = {
  베이스: "cushion",
  아이: "palette",
  브로우: "pencil",
  치크: "blush",
  립: "lip",
  스킨케어: "toner",
  네일: "nail",
  향수: "perfume",
  도구: "brush",
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

/** 직접 입력할 때 고르는 색 */
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
  /** 서버 항목 ID(pouchItemId). 샘플은 p1·p2… */
  id: string;
  cat: PouchCat;
  /** 종류 코드 (API-POUCH-008). 없으면 카테고리 기본 그림 */
  type?: string;
  brand: string;
  name: string;
  /** 호수·컬러명 */
  shade?: string;
  /** 대표 색. 없으면 대체 후보에서 빠진다 */
  color?: string | null;
  /** 카탈로그 제품·호수 연결 (CATALOG 등록). 직접 입력·샘플은 없음 */
  productId?: string | null;
  shadeId?: string | null;
}
