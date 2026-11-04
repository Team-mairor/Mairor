/** 유튜브 영상 썸네일 주소 */
export function videoThumb(ytid: string) {
  return `https://i.ytimg.com/vi/${ytid}/hqdefault.jpg`;
}

/** 분석 진행 단계 (API progressStage) */
export const ANALYSIS_PHASES: [en: string, label: string, from: number][] = [
  ["QUEUED", "대기", 0],
  ["FETCH", "영상 불러오기", 3],
  ["SCENES", "구간 나누기", 12],
  ["DETECT", "제품 인식", 28],
  ["STEPS", "단계 추출", 52],
  ["GUIDE", "가이드 구성", 80],
];
