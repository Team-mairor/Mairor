import type { PouchCat } from "@/domain/pouch";

/** 부위 이름(API)을 화면에 보일 한글 분류로 바꾼다 */
export function partLabel(part: string | null) {
  if (!part) return "기타";
  return (
    (
      {
        foundation: "파운데이션",
        eyeshadow: "아이섀도",
        eyeliner: "아이라이너",
        blush: "블러셔",
        lip: "립",
        brow: "브로우",
        mascara: "마스카라",
        contour: "컨투어",
        highlight: "하이라이터",
        other: "기타",
      } as Record<string, string>
    )[part] ?? part
  );
}

/** 영상에서 찾은 제품의 부위로 파우치 분류를 짐작한다. 알 수 없으면 도구 */
export function pouchCategory(part?: string): PouchCat {
  const value = (part ?? "").toLowerCase();
  if (value.includes("foundation") || value.includes("파운데이션") || value.includes("베이스")) {
    return "베이스";
  }
  if (
    ["eyeshadow", "eyeliner", "mascara"].some((partName) => value.includes(partName)) ||
    /아이섀도|아이라이너|마스카라|아이/.test(value)
  ) {
    return "아이";
  }
  if (value.includes("brow") || value.includes("브로우")) return "브로우";
  if (
    ["blush", "contour", "highlight"].some((partName) => value.includes(partName)) ||
    /블러셔|컨투어|하이라이터|치크/.test(value)
  ) {
    return "치크";
  }
  if (value.includes("lip") || value.includes("립")) return "립";
  return "도구";
}
