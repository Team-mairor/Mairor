import type { MatchKind } from "@/domain/session";

export const GROUPS: { k: MatchKind; label: string; dot: string }[] = [
  { k: "same", label: "보유", dot: "var(--color-sky)" },
  { k: "sub", label: "대체", dot: "var(--color-mint)" },
  { k: "none", label: "없음", dot: "var(--color-blush)" },
];

export const TAG_BG: Record<MatchKind, string> = {
  same: "bg-sky",
  sub: "bg-mint",
  none: "bg-blush",
};
