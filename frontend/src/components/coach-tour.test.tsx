// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CoachTour, type TourStep } from "./coach-tour";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const STEPS: TourStep[] = [
  { target: "a", title: "첫 영역", body: "첫 설명" },
  { target: "missing", title: "없는 영역", body: "보이면 안 됨" },
  { target: "b", title: "둘째 영역", body: "둘째 설명" },
];

let host: HTMLDivElement;
let root: Root;

const render = (steps: TourStep[], onDone: () => void) =>
  act(() => root.render(<CoachTour steps={steps} onDone={onDone} />));
const button = (name: string) =>
  [...document.querySelectorAll("button")].find((b) => b.textContent === name);
const click = (name: string) => act(() => button(name)!.click());

beforeEach(() => {
  host = document.createElement("div");
  host.innerHTML = '<div data-tour="a"></div><div data-tour="b"></div>';
  document.body.appendChild(host);
  const mount = document.createElement("div");
  document.body.appendChild(mount);
  root = createRoot(mount);
});

afterEach(() => {
  act(() => root.unmount());
  document.body.innerHTML = "";
});

describe("CoachTour", () => {
  it("화면에 있는 영역만 순서대로 보여 주고 마지막에 끝낸다", () => {
    const onDone = vi.fn();
    render(STEPS, onDone);
    expect(document.body.textContent).toContain("1 / 2");
    expect(document.body.textContent).toContain("첫 설명");

    click("다음");
    expect(document.body.textContent).toContain("2 / 2");
    expect(document.body.textContent).toContain("둘째 설명");
    expect(document.body.textContent).not.toContain("없는 영역");
    expect(button("건너뛰기")).toBeUndefined();

    click("시작하기");
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("건너뛰기·Esc로 바로 끝낸다", () => {
    const onDone = vi.fn();
    render(STEPS, onDone);
    click("건너뛰기");
    expect(onDone).toHaveBeenCalledTimes(1);

    act(() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
    expect(onDone).toHaveBeenCalledTimes(2);
  });

  it("안내와 같은 렌더에 처음 그려진 영역도 짚는다", () => {
    document.body.removeChild(host);
    const onDone = vi.fn();
    act(() =>
      root.render(
        <>
          <div data-tour="b" />
          <CoachTour steps={STEPS} onDone={onDone} />
        </>,
      ),
    );
    expect(document.body.textContent).toContain("둘째 설명");
    expect(onDone).not.toHaveBeenCalled();
  });

  it("앱 칸이 옮겨지고 zoom으로 줄어도 강조 박스를 영역에 맞춘다", () => {
    // 덮개(앱 칸)는 창의 (100,50)에서 시작하고 800×1200을 0.5배로 줄여 그린다
    const rect = (x: number, y: number, w: number, h: number) =>
      ({ top: y, left: x, width: w, height: h, right: x + w, bottom: y + h }) as DOMRect;
    const spies = [
      vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (
        this: HTMLElement,
      ) {
        if (this.getAttribute("role") === "dialog") return rect(100, 50, 400, 600);
        if (this.dataset.tour === "a") return rect(140, 150, 200, 50);
        return rect(0, 0, 0, 0);
      }),
      vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(800),
      vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(1200),
    ];
    render(STEPS, vi.fn());
    const hole = document.querySelector<HTMLElement>('[role="dialog"] > div')!;
    // 앱 칸 안에서 (80,200) 크기 400×100, 여백 10
    expect(hole.style.top).toBe("190px");
    expect(hole.style.left).toBe("70px");
    expect(hole.style.width).toBe("420px");
    expect(hole.style.height).toBe("120px");
    spies.forEach((s) => s.mockRestore());
  });

  it("짚을 영역이 하나도 없으면 띄우지 않고 끝낸다", () => {
    const onDone = vi.fn();
    render([{ target: "missing", title: "없음", body: "없음" }], onDone);
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(onDone).toHaveBeenCalled();
  });
});
