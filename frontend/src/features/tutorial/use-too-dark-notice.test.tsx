// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TOO_DARK_HOLD_MS, type GaugeDisplay } from "@/domain/gauge";

import { useTooDarkNotice } from "./use-too-dark-notice";

let root: Root;
let element: HTMLDivElement;

const shown = (bar: number | null): GaugeDisplay => ({
  ratio: bar === null ? null : bar / 50,
  bar,
  label: bar === null ? null : "darker",
  reason: null,
  stale: false,
  hueSame: null,
  chromaSame: null,
});

function Probe({
  display,
  enabled = true,
  stepKey = "run:0",
}: {
  display: GaugeDisplay | null;
  enabled?: boolean;
  stepKey?: string;
}) {
  const notice = useTooDarkNotice({ display, enabled, stepKey });
  return <button type="button" data-open={String(notice.open)} onClick={notice.confirm} />;
}

const isOpen = () => element.querySelector("button")?.dataset.open === "true";

const render = async (node: React.ReactNode) => {
  await act(async () => root.render(node));
};
const wait = async (ms: number) => {
  await act(async () => {
    vi.advanceTimersByTime(ms);
  });
};

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

describe("너무 진해요 알림", () => {
  it("진한 상태가 이어져야 열린다", async () => {
    await render(<Probe display={shown(80)} />);
    await wait(TOO_DARK_HOLD_MS - 1);
    expect(isOpen()).toBe(false);
    await wait(1);
    expect(isOpen()).toBe(true);
  });

  it("순간 넘었다가 내려오면 열리지 않는다", async () => {
    await render(<Probe display={shown(80)} />);
    await wait(TOO_DARK_HOLD_MS - 100);
    await render(<Probe display={shown(55)} />);
    await wait(TOO_DARK_HOLD_MS);
    expect(isOpen()).toBe(false);
  });

  it("측정하지 않는 때는 열리지 않는다", async () => {
    await render(<Probe display={shown(90)} enabled={false} />);
    await wait(TOO_DARK_HOLD_MS * 2);
    expect(isOpen()).toBe(false);
  });

  it("확인한 뒤에는 막대가 내려왔다가 다시 넘을 때만 다시 연다", async () => {
    await render(<Probe display={shown(80)} />);
    await wait(TOO_DARK_HOLD_MS);
    expect(isOpen()).toBe(true);

    await act(async () => element.querySelector("button")?.click());
    expect(isOpen()).toBe(false);
    await wait(TOO_DARK_HOLD_MS * 3);
    expect(isOpen()).toBe(false);

    await render(<Probe display={shown(65)} />);
    await render(<Probe display={shown(80)} />);
    await wait(TOO_DARK_HOLD_MS * 3);
    expect(isOpen()).toBe(false);

    await render(<Probe display={shown(55)} />);
    await render(<Probe display={shown(80)} />);
    await wait(TOO_DARK_HOLD_MS);
    expect(isOpen()).toBe(true);
  });

  it("열려 있다가 막대가 충분히 내려오면 저절로 닫힌다", async () => {
    await render(<Probe display={shown(80)} />);
    await wait(TOO_DARK_HOLD_MS);
    expect(isOpen()).toBe(true);

    // 아직 내려오는 중(60 이상)에는 열린 채로 둔다
    await render(<Probe display={shown(65)} />);
    expect(isOpen()).toBe(true);

    await render(<Probe display={shown(55)} />);
    expect(isOpen()).toBe(false);

    // 닫힌 뒤 중간 값으로 올라와도 다시 열리지 않는다
    await render(<Probe display={shown(65)} />);
    await wait(TOO_DARK_HOLD_MS * 2);
    expect(isOpen()).toBe(false);

    // 다시 진해지면 다시 알린다
    await render(<Probe display={shown(80)} />);
    await wait(TOO_DARK_HOLD_MS);
    expect(isOpen()).toBe(true);
  });

  it("측정이 멈춘 동안에는 내려갔다고 보지 않아 열린 채로 둔다", async () => {
    await render(<Probe display={shown(80)} />);
    await wait(TOO_DARK_HOLD_MS);
    expect(isOpen()).toBe(true);

    await render(<Probe display={{ ...shown(30), stale: true }} />);
    expect(isOpen()).toBe(true);
  });

  it("단계가 바뀌면 닫히고 새 단계에서 다시 알린다", async () => {
    await render(<Probe display={shown(80)} />);
    await wait(TOO_DARK_HOLD_MS);
    expect(isOpen()).toBe(true);

    await render(<Probe display={shown(80)} stepKey="run:1" />);
    expect(isOpen()).toBe(false);
    await wait(TOO_DARK_HOLD_MS);
    expect(isOpen()).toBe(true);
  });
});
