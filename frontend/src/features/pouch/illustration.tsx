import { ILL_SIZE, POUCH_TYPES, type PouchCat, type PouchItem } from "./catalog";

/** 선화+채움 두 장으로 된 옛 일러스트. 채움을 제품 색으로 물들인다 */
const TINTED = new Set(["lip", "compact", "jar", "spray", "pencil", "brush"]);

export function typeOf(p: Pick<PouchItem, "cat" | "type">) {
  const types = POUCH_TYPES[p.cat] ?? POUCH_TYPES["도구"];
  return types.find((t) => t[0] === p.type) ?? types[0];
}

/** 종류 일러스트 키와 스티커 크기. 면적을 비슷하게 맞춘다 (최대 230px) */
export function illOf(p: Pick<PouchItem, "cat" | "type">) {
  const key = typeOf(p)[1];
  const [w, h] = ILL_SIZE[key] ?? [160, 200];
  const sc = Math.min(Math.sqrt(30000 / (w * h)), 230 / Math.max(w, h));
  return { key, width: Math.round(w * sc), height: Math.round(h * sc), tinted: TINTED.has(key) };
}

export function illSrc(key: string) {
  return TINTED.has(key) ? `/ill/${key}-line.png` : `/ill/${key}.png`;
}

/**
 * 제품 일러스트. 선화형은 채움 그림을 마스크로 써서 CSS만으로 색을 입힌다.
 * (프로토타입은 캔버스로 합성했다)
 */
export function Illustration({
  item,
  color,
  className,
  size,
  width,
}: {
  item: Pick<PouchItem, "cat" | "type">;
  color?: string | null;
  className?: string;
  /** 지정하면 이 크기 안에 맞춘다 (종류 선택 칩 등) */
  size?: number;
  /** 지정하면 이 폭에 비율을 유지해 맞춘다 */
  width?: number;
}) {
  const ill = illOf(item);
  const style = size
    ? { width: size, height: size }
    : width
      ? { width, height: Math.round((width * ill.height) / ill.width) }
      : { width: ill.width, height: ill.height };
  const fit = size ? "contain" : "100% 100%";
  return (
    <span
      className={className}
      style={{ position: "relative", display: "block", ...style }}
      aria-hidden
    >
      {ill.tinted && (
        <span
          className="absolute inset-0"
          style={{
            background: color ?? "#F4B6CF",
            maskImage: `url(/ill/${ill.key}-fill.png)`,
            maskSize: fit,
            maskRepeat: "no-repeat",
            maskPosition: "center",
            WebkitMaskImage: `url(/ill/${ill.key}-fill.png)`,
            WebkitMaskSize: fit,
            WebkitMaskRepeat: "no-repeat",
            WebkitMaskPosition: "center",
          }}
        />
      )}
      <span
        className="absolute inset-0"
        style={{
          backgroundImage: `url(${illSrc(ill.key)})`,
          backgroundSize: fit,
          backgroundRepeat: "no-repeat",
          backgroundPosition: "center",
        }}
      />
    </span>
  );
}

export type { PouchCat };
