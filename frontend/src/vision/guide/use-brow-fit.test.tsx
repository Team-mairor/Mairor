// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearFacePhoto, saveFaceBrows, saveFacePhoto } from "@/vision/face/registered-photo";

import type { GuideStep } from "./types";
import { useBrowFit } from "./use-brow-fit";

vi.mock("@/vision/overlay", () => ({
  loadFaceMesh: () => Promise.resolve({ triangles: [], uv: [] }),
}));
vi.mock("./brow-fit", () => ({
  findBrows: vi.fn(),
  fitBrowStep: (step: GuideStep) => ({ ...step, title: "맞춘 눈썹" }),
}));

const step: GuideStep = {
  stepId: "s8",
  order: 1,
  title: "기본 눈썹",
  regions: ["rightBrow", "leftBrow"],
  guides: [],
  source: "template",
};

function Title() {
  return <p>{useBrowFit(step, "run")?.title}</p>;
}

let element: HTMLDivElement;
let root: Root;
beforeEach(() => {
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  element = document.createElement("div");
  document.body.append(element);
  root = createRoot(element);
});
afterEach(async () => {
  await act(async () => root.unmount());
  element.remove();
  clearFacePhoto();
});

describe("원래 눈썹 맞춤 시점", () => {
  it("튜토리얼을 연 뒤에 눈썹 분석이 끝나도 그때 가이드를 맞춘다", async () => {
    const photo = new Blob(["face"]);
    saveFacePhoto("run", photo);
    await act(async () => root.render(<Title />));
    expect(element.textContent).toBe("기본 눈썹");

    await act(async () => saveFaceBrows("run", photo, { rightBrow: [] }));
    expect(element.textContent).toBe("맞춘 눈썹");
  });

  it("다른 실행이나 다시 찍기 전 사진의 눈썹은 쓰지 않는다", async () => {
    const old = new Blob(["old"]);
    saveFacePhoto("run", old);
    await act(async () => root.render(<Title />));
    await act(async () => saveFacePhoto("run", new Blob(["new"])));
    await act(async () => saveFaceBrows("run", old, { rightBrow: [] }));
    await act(async () => saveFaceBrows("other", old, { rightBrow: [] }));
    expect(element.textContent).toBe("기본 눈썹");
  });
});
