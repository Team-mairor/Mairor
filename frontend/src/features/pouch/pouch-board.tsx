"use client";

import type { ReactNode } from "react";

import type { PouchItem } from "@/domain/pouch/catalog";
import { cn } from "@/lib/utils";

import { Illustration } from "./illustration";

/** 스티커 자리 (x%, y%, 회전, 배율, z). 최대 5개 */
const SLOTS: [number, number, number, number, number][] = [
  [16, 50, -14, 1.1, 2],
  [36, 76, 10, 0.95, 3],
  [55, 46, -6, 1.15, 1],
  [64, 78, 14, 0.9, 4],
  [83, 44, -9, 1, 2],
];
const SLOTS_TALL: typeof SLOTS = [
  [16, 42, -14, 1.15, 2],
  [36, 72, 10, 1, 3],
  [55, 40, -6, 1.2, 1],
  [62, 76, 14, 0.95, 4],
  [82, 36, -9, 1.05, 2],
];

export function Sticker({
  item,
  slot,
  onClick,
  dim = false,
  delay,
  size = "md",
}: {
  item: PouchItem;
  slot: (typeof SLOTS)[number];
  onClick?: () => void;
  /** 온보딩 예시: 흐리게 */
  dim?: boolean;
  /** 떨어지는 등장 연출 지연 */
  delay?: string;
  size?: "md" | "lg";
}) {
  const [x, y, r, s, z] = slot;
  const lr = -r * 0.6 + (z % 2 ? 3 : -3);
  return (
    <div
      className="absolute"
      style={{
        left: `${x}%`,
        top: `${y}%`,
        zIndex: z,
        animation: delay ? `mr-drop 760ms cubic-bezier(.2,.9,.25,1.15) ${delay} both` : undefined,
      }}
    >
      <button
        type="button"
        onClick={onClick}
        className="relative flex flex-col items-center transition-[translate] hover:-translate-y-1.5"
        style={{
          transform: `translate(-50%,-50%) rotate(${r}deg) scale(${s})`,
          opacity: dim ? 0.42 : 1,
          filter: dim
            ? "grayscale(.6)"
            : "drop-shadow(0 12px 16px color-mix(in srgb, var(--color-night) 20%, transparent))",
        }}
        aria-label={`${item.brand} ${item.name} 수정`}
      >
        <Illustration
          item={item}
          color={item.color}
          className="[filter:drop-shadow(6px_0_0_#fff)_drop-shadow(-6px_0_0_#fff)_drop-shadow(0_6px_0_#fff)_drop-shadow(0_-6px_0_#fff)]"
        />
        <span
          className={cn(
            "relative flex flex-col items-center rounded-2xl bg-white shadow-float",
            size === "lg"
              ? "-mt-3.5 max-w-[300px] gap-1 px-[22px] pt-3 pb-3.5"
              : "-mt-2.5 max-w-[240px] gap-px px-4 py-2",
          )}
          style={{ transform: `rotate(${lr}deg)` }}
        >
          <span
            className={cn(
              "whitespace-nowrap",
              size === "lg" ? "text-[24px] font-semibold text-navy" : "text-[18px] text-mute",
            )}
          >
            {item.cat} · {item.brand}
          </span>
          <span
            className={cn(
              "text-center font-serif leading-[1.1] text-ink",
              size === "lg" ? "text-[34px]" : "text-[23px]",
            )}
          >
            {item.name}
          </span>
        </span>
      </button>
    </div>
  );
}

/**
 * 모눈 배경의 파우치 보드. 최근 제품 최대 5개를 스티커로 보여 준다.
 * scale: 스티커 좌표계를 보드 크기에 맞춰 줄이는 배율 (홈 .6, 마이 .66, 온보딩 .62)
 */
export function PouchBoard({
  items,
  onEdit,
  scale = 0.6,
  slots = "wide",
  grid = 44,
  dim = false,
  animate = false,
  children,
  className,
  stickerSize,
}: {
  items: PouchItem[];
  onEdit?: (item: PouchItem) => void;
  scale?: number;
  slots?: "wide" | "tall";
  grid?: number;
  dim?: boolean;
  animate?: boolean;
  /** 보드 위에 얹는 라벨·버튼 */
  children?: ReactNode;
  className?: string;
  stickerSize?: "md" | "lg";
}) {
  const top = items.slice(0, 5);
  const table = slots === "tall" ? SLOTS_TALL : SLOTS;
  return (
    <div
      className={cn("relative overflow-hidden rounded-3xl border border-line bg-white", className)}
      style={{
        backgroundImage:
          "linear-gradient(color-mix(in srgb, var(--color-night) 10%, transparent) 1px,transparent 1px),linear-gradient(90deg,color-mix(in srgb, var(--color-night) 10%, transparent) 1px,transparent 1px)",
        backgroundSize: `${grid}px ${grid}px`,
        backgroundPosition: "-1px -1px",
      }}
    >
      {children}
      <div
        className="absolute top-0 left-0 origin-top-left"
        style={{
          width: `${100 / scale}%`,
          height: `${100 / scale}%`,
          transform: `scale(${scale})`,
        }}
      >
        {top.map((p, i) => (
          <Sticker
            key={p.id}
            item={p}
            slot={table[i]}
            onClick={() => onEdit?.(p)}
            dim={dim}
            delay={animate ? `${350 + i * 240}ms` : undefined}
            size={stickerSize}
          />
        ))}
      </div>
    </div>
  );
}
