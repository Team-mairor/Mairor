// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useFinalCountdown } from "./use-final-countdown";

let root: Root;
let element: HTMLDivElement;

function Probe({ interrupt }: { interrupt: readonly boolean[] }) {
  const { countdown, start } = useFinalCountdown({ onFire: vi.fn(), interrupt });
  return <button type="button" data-count={String(countdown)} onClick={start} />;
}

const render = async (interrupt: readonly boolean[]) => {
  await act(async () => root.render(<Probe interrupt={interrupt} />));
};
const count = () => element.querySelector("button")?.dataset.count;
const press = async () => act(async () => element.querySelector("button")?.click());
const wait = async (ms: number) =>
  act(async () => {
    vi.advanceTimersByTime(ms);
  });

beforeEach(() => {
  vi.useFakeTimers();
  Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
  element = document.createElement("div");
  document.body.append(element);
  root = createRoot(element);
});
afterEach(async () => {
  await act(async () => root.unmount());
  element.remove();
  vi.useRealTimers();
});

describe("마지막 사진 카운트다운", () => {
  it("중단 조건이 켜지면 진행 중인 카운트다운을 접는다", async () => {
    await render([false, false, false]);
    await press();
    expect(count()).toBe("3");

    await render([false, true, false]);
    await wait(1);
    expect(count()).toBe("null");
  });

  it("이미 다른 조건이 켜진 채 시작했어도 조건이 하나 더 바뀌면 접는다", async () => {
    await render([true, false, false]);
    await press();
    expect(count()).toBe("3");

    await render([true, true, false]);
    await wait(1);
    expect(count()).toBe("null");
  });
});
