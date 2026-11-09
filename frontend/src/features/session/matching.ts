import type { PouchItem } from "@/features/pouch";

import type { RunState } from "./session-provider";
import type { RefProduct } from "./types";

export type MatchKind = "same" | "sub" | "none";

export interface MatchResult {
  kind: MatchKind;
  /** 내가 쓸 제품. 없음이면 null. 파우치 제품이면 id가 있다 */
  p: { id?: string; brand: string; name: string; shade?: string; color?: string | null } | null;
}

/** 대소문자·공백 차이만 있으면 같은 이름으로 본다 */
export function sameName(a: string, b: string) {
  const norm = (t: string) => t.toLowerCase().replace(/\s+/g, "");
  const x = norm(a);
  return x.length > 0 && x === norm(b);
}

/** 샘플: 파우치에 같은 이름의 제품이 있으면 보유 */
export function hasSame(ref: RefProduct, pouch: PouchItem[]) {
  return pouch.some((p) => sameName(p.name, ref.name));
}

/**
 * 영상 속 제품 r의 매칭 결과. 프로토타입 prodFor와 같은 규칙:
 * 사용자가 고른 제품 > 보유 > 추천 대체(켜져 있을 때) > 없음
 * 파우치가 비어 있으면 모든 단계가 없음. emptyPouch는 ?empty=1 확인용 강제값
 */
export function matchFor(
  r: RefProduct,
  run: Pick<RunState, "choice" | "subOn">,
  pouch: PouchItem[],
  emptyPouch = false,
): MatchResult {
  const ch = run.choice[r.id];
  if (emptyPouch || pouch.length === 0 || ch?.kind === "none") return { kind: "none", p: null };
  if (ch?.kind === "pouch") {
    const pp = pouch.find((x) => x.id === ch.id);
    if (pp) return { kind: sameName(pp.name, r.name) ? "same" : "sub", p: pp };
  }
  // 샘플 플래그(r.have)가 아니라 지금 파우치에서 찾은 제품을 돌려준다. 지워진 제품이 보유로 남지 않는다
  const same = pouch.find((p) => sameName(p.name, r.name));
  if (same) return { kind: "same", p: same };
  if (r.sub && run.subOn[r.id] !== false) return { kind: "sub", p: r.sub };
  return { kind: "none", p: null };
}

/** 리포트에 남기는 단계별 확정 제품 (저장 시점 snapshot) */
export interface ReportStep {
  kind: MatchKind;
  used: { brand: string; name: string } | null;
}

export function snapshotSteps(
  refs: RefProduct[],
  run: Pick<RunState, "choice" | "subOn">,
  pouch: PouchItem[],
): ReportStep[] {
  return refs.map((r) => {
    const m = matchFor(r, run, pouch);
    return { kind: m.kind, used: m.p ? { brand: m.p.brand, name: m.p.name } : null };
  });
}

export function matchCounts(
  refs: RefProduct[],
  run: Pick<RunState, "choice" | "subOn">,
  pouch: PouchItem[],
  emptyPouch = false,
) {
  let same = 0;
  let sub = 0;
  let none = 0;
  refs.forEach((r) => {
    const k = matchFor(r, run, pouch, emptyPouch).kind;
    if (k === "same") same++;
    else if (k === "sub") sub++;
    else none++;
  });
  return { same, sub, none };
}
