// 고정 기준은 덮어쓰지 않는다. Node 22.18+; npm run fixtures:compare
import { readFileSync, writeFileSync } from "node:fs";

import { REGIONS } from "../src/features/face/regions.ts";
import { buildDefaultGuideSet } from "../src/features/guide/default-guides.ts";
const read = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url), "utf8"));
const mesh = {
  ...read("../../shared/face-mesh/triangles.v1.json"),
  ...read("../../shared/face-mesh/uv.v1.json"),
};
const current = buildDefaultGuideSet(mesh, REGIONS);
current.steps = current.steps.filter((s) => ["blush", "brow"].includes(s.stepId));
writeFileSync(
  new URL("../public/fixtures/guides/compare-candidate.json", import.meta.url),
  JSON.stringify(current, null, 2) + "\n",
);
