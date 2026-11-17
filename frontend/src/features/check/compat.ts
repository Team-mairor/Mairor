import type { GuideStepModel, Makeup } from "@/features/guide";
import type { PouchItem } from "@/features/pouch";

/** 화장 종류별 후보 파우치 종류. 확정되지 않은 종류와 쉐딩은 넣지 않는다 */
export const COMPAT_TYPES: Record<Makeup, readonly string[]> = {
  foundation: ["쿠션", "파운데이션"],
  eyeshadow: ["섀도우 팔레트"],
  eyeliner: ["아이라이너"],
  mascara: ["마스카라"],
  brow: ["브로우 펜슬"],
  blush: ["블러셔"],
  highlight: ["하이라이터"],
  lip: ["립스틱", "립글로스", "립틴트", "리퀴드 립"],
  contour: [],
  other: [],
};

/** 수동 선택도 서버 추천과 같이 단계의 화장 종류에 맞는 종류(블러셔·하이라이터 등)이고 대표 색상이 있는 제품만 허용한다. */
export function isCompatible(step: Pick<GuideStepModel, "makeup">, item: PouchItem) {
  if (!item.color) return false;
  return !!item.type && COMPAT_TYPES[step.makeup].includes(item.type);
}
