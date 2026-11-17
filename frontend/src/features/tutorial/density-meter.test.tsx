import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DensityMeter, gaugeVisualValue } from "./density-meter";

describe("DensityMeter", () => {
  it("목표선과 현재 위치를 따로 표시한다", () => {
    const html = renderToStaticMarkup(<DensityMeter value={32} color="#9be8f6" blocked={false} />);

    expect(html).toContain("목표");
    expect(html).toContain("내 위치");
    expect(html).toContain("left:34.99%");
    expect(html).toContain("현재 35, 목표 50");
  });

  it("측정이 막혀도 게이지 틀을 유지한다", () => {
    const html = renderToStaticMarkup(<DensityMeter value={44} color="#9be8f6" blocked />);

    expect(html).toContain("data-track");
    expect(html).toContain("data-current");
    expect(html).toContain("width:45.14%");
    expect(html).not.toContain("opacity:");
    expect(html).not.toContain("측정 중</span>");
  });

  it("첫 측정 전에도 시작점과 최소 채움을 보여 준다", () => {
    const html = renderToStaticMarkup(<DensityMeter value={null} color="#9be8f6" blocked />);

    expect(html).toContain("width:4%");
    expect(html).toContain("left:4%");
    expect(html).toContain('data-measuring="true"');
    expect(html).toContain("측정 시작점");
  });

  it("목표 전 구간만 완화하고 시작과 목표 이후는 그대로 둔다", () => {
    expect(gaugeVisualValue(0)).toBe(0);
    expect(gaugeVisualValue(25)).toBe(28.72);
    expect(gaugeVisualValue(50)).toBe(50);
    expect(gaugeVisualValue(70)).toBe(70);
  });
});
