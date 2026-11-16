import { describe, expect, it } from "vitest";

import {
  BaselineCollector,
  buildBaseline,
  FRAME_GAP_MS,
  FrontCenter,
  goodFrame,
  type FrameQuality,
} from "./baseline";
import { GRID, MEASURED } from "./spec";

const q = (over: Partial<FrameQuality> = {}): FrameQuality => ({
  yaw: 0,
  pitch: 0,
  roll: 0,
  eyes: 1,
  ...over,
});
const first = [...MEASURED.keys()].find((k) => MEASURED[k])!;
const grid = (l: number) => {
  const g = new Float32Array(GRID * GRID * 3).fill(NaN);
  for (let k = 0; k < GRID * GRID; k++) if (MEASURED[k]) g.set([l, 10, 20], k * 3);
  return g;
};

describe("기준 사진 고르기", () => {
  it("얼굴 등록과 같은 정면 각도에 눈을 뜬 사진만 쓴다", () => {
    expect(goodFrame(q(), 0)).toBe(true);
    expect(goodFrame(q({ yaw: 0.25 }), 0)).toBe(false);
    expect(goodFrame(q({ roll: 0.2 }), 0)).toBe(false);
    expect(goodFrame(q({ eyes: 0.1 }), 0)).toBe(false);
  });

  it("카메라가 눈보다 낮아 정면이 pitch −0.23인 사람도 그 사람 정면 둘레 사진을 쓴다", () => {
    const center = new FrontCenter();
    for (let i = 0; i < 30; i++) center.push(q({ pitch: -0.23 + (i % 3) * 0.01 }));
    expect(center.value).toBeCloseTo(-0.22, 5);
    expect(goodFrame(q({ pitch: -0.3 }), center.value!)).toBe(true);
    expect(goodFrame(q({ pitch: 0.05 }), center.value!)).toBe(false);
  });

  it("정면을 정할 때 고개를 돌렸거나 눈을 감은 사진은 세지 않고, 다 모으기 전에는 정하지 않는다", () => {
    const center = new FrontCenter();
    for (let i = 0; i < 29; i++) center.push(q({ pitch: 0.1 }));
    center.push(q({ pitch: -0.5, yaw: 0.4 }));
    center.push(q({ pitch: -0.5, eyes: 0 }));
    expect(center.value).toBeNull();
    center.push(q({ pitch: 0.1 }));
    expect(center.value).toBeCloseTo(0.1, 5);
  });
});

describe("기준 만들기", () => {
  it("사진 중 한 장에 손이 지나가도 칸마다 가운데 값이라 흔들리지 않는다", () => {
    const grids = [grid(60), grid(61), grid(20), grid(60), grid(62)];
    const base = buildBaseline(grids);
    expect(base.lab[first * 3]).toBe(60);
    expect(base.cells[first]).toBe(1);
    expect(base.frames).toBe(5);
  });

  it("어느 사진에서도 색이 없던 칸은 기준에서 뺀다", () => {
    const empty = grid(60);
    empty.fill(NaN, first * 3, first * 3 + 3);
    const base = buildBaseline([empty]);
    expect(base.cells[first]).toBe(0);
    expect(Number.isNaN(base.lab[first * 3])).toBe(true);
  });

  it("좋은 사진을 간격을 두고 15장 모아야 기준을 낸다", () => {
    const collector = new BaselineCollector();
    let now = 0;
    expect(collector.wants(q({ yaw: 0.5 }), 0, now)).toBe(false);
    for (let i = 0; i < 15; i++) {
      expect(collector.build()).toBeNull();
      expect(collector.wants(q(), 0, now)).toBe(true);
      collector.push(grid(60), now);
      expect(collector.wants(q(), 0, now + FRAME_GAP_MS / 2)).toBe(false);
      now += FRAME_GAP_MS;
    }
    expect(collector.done).toBe(true);
    expect(collector.wants(q(), 0, now)).toBe(false);
    expect(collector.build()?.frames).toBe(15);
  });
});
