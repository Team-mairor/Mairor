import { describe, expect, it } from "vitest";

import { BASIC_PHOTO_FRAME } from "./frame";
import { drawPhotoStamp, formatStampDate } from "./stamp";

function fakeCanvas() {
  const texts: { text: string; x: number; y: number; font: string }[] = [];
  const ctx = {
    font: "",
    fillStyle: "",
    textAlign: "",
    textBaseline: "",
    letterSpacing: "",
    save() {},
    restore() {},
    measureText: () => ({ width: 200 }),
    fillText(text: string, x: number, y: number) {
      texts.push({ text, x, y, font: this.font });
    },
  };
  return { canvas: { getContext: () => ctx } as unknown as HTMLCanvasElement, texts };
}

const fonts = { serif: "Serif", sans: "Sans" };

describe("formatStampDate", () => {
  it("연.월.일을 두 자리로 맞춘다", () => {
    expect(formatStampDate(new Date(2026, 10, 18))).toBe("2026.11.18");
    expect(formatStampDate(new Date(2026, 0, 5))).toBe("2026.01.05");
  });
});

describe("drawPhotoStamp", () => {
  it("mairor 글씨가 있으면 가장 오른쪽 칸 끝에 mairor를, 그 왼쪽에 날짜를 같은 밑선에 그린다", () => {
    const { canvas, texts } = fakeCanvas();
    drawPhotoStamp(canvas, BASIC_PHOTO_FRAME, {
      date: "2026.11.18",
      color: "#fff",
      mairor: true,
      fonts,
    });

    expect(texts.map((item) => item.text)).toEqual(["mairor", "2026.11.18"]);
    const [mark, date] = texts;
    expect(mark.x).toBe(930 + 825);
    expect(mark.y).toBe(BASIC_PHOTO_FRAME.output.height - 48);
    expect(date.y).toBe(mark.y);
    expect(date.x).toBeLessThan(mark.x - 160);
  });

  it("mairor를 끄면 날짜만 같은 자리에 그린다", () => {
    const { canvas, texts } = fakeCanvas();
    drawPhotoStamp(canvas, BASIC_PHOTO_FRAME, {
      date: "2026.11.18",
      color: "#fff",
      mairor: false,
      fonts,
    });
    expect(texts.map((item) => item.text)).toEqual(["2026.11.18"]);
    expect(texts[0].x).toBe(930 + 825 - 160 - 40);
  });
});
