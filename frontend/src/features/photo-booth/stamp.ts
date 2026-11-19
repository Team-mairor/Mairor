import type { PhotoFrameTemplate } from "./frame";

/** 프레임 우측 하단의 촬영 날짜·mairor 글씨. 합성 뒤 같은 canvas에 덧그려 저장 사진에도 들어간다. */
export interface PhotoStamp {
  /** 촬영 날짜. formatStampDate로 만든 문자열 */
  readonly date: string;
  readonly color: string;
  /** 프레임 이미지에 mairor 글씨가 없을 때만 직접 그린다 */
  readonly mairor: boolean;
  /** 기본 출력 크기 대비 글씨·여백 배율 */
  readonly scale?: number;
  readonly fonts: StampFonts;
}

export interface StampFonts {
  readonly serif: string;
  readonly sans: string;
}

const MARK_TEXT = "mairor";
/** SSAFY 프레임 이미지에 들어 있는 mairor 글씨 너비(px). 직접 그릴 때도 같은 크기로 맞춘다 */
const MARK_WIDTH = 160;
const MARK_GAP = 40;
const DATE_FONT_SIZE = 34;
/** 글씨 밑선과 프레임 아래 끝 사이 여백 */
const BASELINE_MARGIN = 48;

export function formatStampDate(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}.${pad(date.getMonth() + 1)}.${pad(date.getDate())}`;
}

/** 글씨에 쓰는 서체 이름을 읽고 canvas에서 쓸 수 있게 불러온다. 실패하면 기본 서체로 그린다 */
export async function loadStampFonts(): Promise<StampFonts> {
  const style = getComputedStyle(document.documentElement);
  const serif = style.getPropertyValue("--font-instrument-serif").trim() || "serif";
  const sans = style.getPropertyValue("--font-instrument-sans").trim() || "sans-serif";
  try {
    await Promise.all([
      document.fonts.load(`italic 80px ${serif}`, MARK_TEXT),
      document.fonts.load(`600 ${DATE_FONT_SIZE}px ${sans}`, "0123456789."),
    ]);
  } catch {
    // 서체를 못 불러와도 기본 서체로 그린다
  }
  return { serif, sans };
}

/** 가장 오른쪽 칸의 오른쪽 끝에 mairor 글씨를, 그 왼쪽에 날짜를 같은 밑선에 그린다. */
export function drawPhotoStamp(
  canvas: HTMLCanvasElement,
  frame: PhotoFrameTemplate,
  stamp: PhotoStamp,
): void {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const scale = stamp.scale ?? 1;
  const markWidth = MARK_WIDTH * scale;
  const markGap = MARK_GAP * scale;
  const right = Math.max(...frame.slots.map((slot) => slot.x + slot.width));
  const baseline = frame.output.height - BASELINE_MARGIN * scale;

  ctx.save();
  try {
    ctx.fillStyle = stamp.color;
    ctx.textAlign = "right";
    ctx.textBaseline = "alphabetic";

    if (stamp.mairor) {
      ctx.font = `italic 100px ${stamp.fonts.serif}`;
      const measured = ctx.measureText(MARK_TEXT).width;
      const size = measured > 0 ? (100 * markWidth) / measured : 80 * scale;
      ctx.font = `italic ${size}px ${stamp.fonts.serif}`;
      ctx.fillText(MARK_TEXT, right, baseline);
    }

    ctx.font = `600 ${DATE_FONT_SIZE * scale}px ${stamp.fonts.sans}`;
    ctx.letterSpacing = `${2 * scale}px`;
    ctx.fillText(stamp.date, right - markWidth - markGap, baseline);
  } finally {
    ctx.restore();
  }
}
