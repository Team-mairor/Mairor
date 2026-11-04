// 파우치 카테고리·종류·일러스트 크기. 화면과 매칭이 함께 쓰는 고정값

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
