import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * 폴더 계층과 순환 검사. 계층(app → features → domain → vision)은 eslint가 막고,
 * 같은 계층 안의 폴더끼리 서로 가져오는 순환은 여기서 잡는다. 테스트 파일도 센다.
 */
const SRC = join(__dirname);

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : /\.(ts|tsx)$/.test(name) ? [path] : [];
  });
}

/** features/home/x.ts → "features/home". 폴더 단위가 아닌 파일은 null */
function nodeOf(path: string) {
  const m = relative(SRC, path)
    .replaceAll("\\", "/")
    .match(/^(features|domain|vision)\/([^/]+)\//);
  return m ? `${m[1]}/${m[2]}` : null;
}

/** import · 동적 import · require · vi.mock 계열이 불러오는 경로를 모두 뽑는다(따옴표 종류 무관) */
function specifiersOf(text: string) {
  return [
    ...text.matchAll(
      /(?:\bfrom|\bimport|\brequire|\bvi\.(?:mock|doMock|unmock|importActual|importMock))\s*(?:<[^>\n]*>)?\s*\(?\s*["'`]([^"'`\n]+)["'`]/g,
    ),
  ].map((m) => m[1]);
}

/** 불러오는 경로가 가리키는 폴더 단위(features/home 등). 패키지이거나 폴더 단위가 아니면 null */
function targetOf(spec: string, fromFile: string) {
  const path = spec.startsWith("@/")
    ? spec.slice(2)
    : spec.startsWith(".")
      ? relative(SRC, resolve(dirname(fromFile), spec)).replaceAll("\\", "/")
      : null;
  const m = path?.match(/^(features|domain|vision)\/([^/]+)/);
  return m ? `${m[1]}/${m[2]}` : null;
}

function graph() {
  const edges = new Map<string, Set<string>>();
  for (const path of files(SRC)) {
    const from = nodeOf(path);
    if (!from) continue;
    for (const spec of specifiersOf(readFileSync(path, "utf8"))) {
      const to = targetOf(spec, path);
      if (!to || to === from) continue;
      if (!edges.has(from)) edges.set(from, new Set());
      edges.get(from)!.add(to);
    }
  }
  return edges;
}

function cycles(edges: Map<string, Set<string>>) {
  const found = new Set<string>();
  const done = new Set<string>();
  const visit = (node: string, path: string[]) => {
    for (const next of edges.get(node) ?? []) {
      const at = path.indexOf(next);
      if (at >= 0) found.add([...path.slice(at), next].join(" -> "));
      else if (!done.has(next)) visit(next, [...path, next]);
    }
    done.add(node);
  };
  for (const node of edges.keys()) visit(node, [node]);
  return [...found];
}

describe("폴더 구조", () => {
  const edges = graph();

  it("폴더끼리 서로 가져오는 순환이 없다", () => {
    expect(cycles(edges)).toEqual([]);
  });

  it("vision은 domain·features를, domain은 features를 가져오지 않는다", () => {
    const bad: string[] = [];
    for (const [from, tos] of edges)
      for (const to of tos) {
        const [a] = from.split("/");
        const [b] = to.split("/");
        if ((a === "vision" && b !== "vision") || (a === "domain" && b === "features"))
          bad.push(`${from} -> ${to}`);
      }
    expect(bad).toEqual([]);
  });

  it("동적 import·require·vi.importActual·상대 경로로 가져와도 알아본다", () => {
    const text = [
      'import { a } from "@/features/a";',
      "const b = await import('@/domain/b');",
      'const c = require("../../features/c");',
      'const d = await vi.importActual<typeof import("@/vision/d")>("@/vision/d");',
      "vi.doMock(`@/domain/e`);",
      'import "@/features/f";',
      'import { z } from "react";',
    ].join("\n");
    const from = join(SRC, "domain/gauge/x.ts");
    expect(specifiersOf(text).map((spec) => targetOf(spec, from))).toEqual([
      "features/a",
      "domain/b",
      "features/c",
      "vision/d",
      "domain/e",
      "features/f",
      null,
    ]);
  });

  it("순환 검사 자체가 순환을 알아본다", () => {
    const sample = new Map([
      ["features/a", new Set(["features/b"])],
      ["features/b", new Set(["features/a"])],
    ]);
    expect(cycles(sample)).toEqual(["features/a -> features/b -> features/a"]);
  });
});
