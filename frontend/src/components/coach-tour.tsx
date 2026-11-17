"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { PillButton } from "@/components/ui/pill-button";

export type TourStep = {
  /** 강조할 요소의 data-tour 값 */
  target: string;
  title: string;
  body: string;
};

/** 덮개 안 좌표(CSS px). vh는 덮개 높이 */
type Box = { top: number; left: number; width: number; height: number; vh: number };

const PAD = 10;
const GAP = 18;
/** 말풍선이 들어갈 높이. 영역 아래·위 어디에도 이만큼 없으면 화면 아래에 붙인다 */
const BUBBLE_H = 260;

const find = (target: string) =>
  typeof document === "undefined"
    ? null
    : document.querySelector<HTMLElement>(`[data-tour="${target}"]`);

/** 첫 진입 안내. 어두운 덮개 위에 영역을 하나씩 비워 보여 주고 설명을 띄운다. 화면에 없는 영역은 건너뛴다 */
export function CoachTour({ steps, onDone }: { steps: TourStep[]; onDone: () => void }) {
  const [index, setIndex] = useState(0);
  const [box, setBox] = useState<Box | null>(null);
  const next = useRef<HTMLButtonElement>(null);
  const root = useRef<HTMLDivElement>(null);
  // 화면에 있는 영역만 순서에 넣는다. 안내와 같은 렌더에 영역이 처음 그려질 수 있어 DOM에 반영된 뒤 찾는다
  const [shown, setShown] = useState<TourStep[] | null>(null);
  useLayoutEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 영역은 DOM에 그려진 뒤에만 찾을 수 있다
    setShown(steps.filter((s) => find(s.target)));
  }, [steps]);
  const step = shown?.[index];
  const total = shown?.length ?? 0;
  const last = index >= total - 1;

  useEffect(() => {
    if (shown && !step) onDone();
  }, [shown, step, onDone]);

  useLayoutEffect(() => {
    const el = step && find(step.target);
    if (!el) return;
    el.scrollIntoView?.({ block: "nearest" });
    // 앱 칸(#app)의 contain·zoom 때문에 fixed 덮개가 창이 아니라 앱 칸 기준으로 놓일 수 있다.
    // 영역과 덮개를 같은 방식으로 재서 덮개 기준 거리로 바꾸고, 잰 크기와 CSS 크기의 비율로 zoom을 되돌린다
    const measure = () => {
      const o = root.current;
      if (!o) return;
      const base = o.getBoundingClientRect();
      const k = base.width / o.offsetWidth || 1;
      const r = el.getBoundingClientRect();
      setBox({
        top: (r.top - base.top) / k,
        left: (r.left - base.left) / k,
        width: r.width / k,
        height: r.height / k,
        vh: o.offsetHeight,
      });
    };
    measure();
    window.addEventListener("resize", measure);
    // 본문이 스크롤 영역 안에 있어서 캡처로 받는다
    window.addEventListener("scroll", measure, true);
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [step]);

  useEffect(() => {
    next.current?.focus();
  }, [index]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onDone();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onDone]);

  if (!step) return null;

  const below = box && box.top + box.height + PAD + GAP + BUBBLE_H <= box.vh;
  const above = box && box.top - PAD - GAP - BUBBLE_H >= 0;
  const bubbleStyle = !box
    ? { bottom: 24 }
    : below
      ? { top: box.top + box.height + PAD + GAP }
      : above
        ? { bottom: box.vh - box.top + PAD + GAP }
        : { bottom: 24 };

  return (
    <div
      ref={root}
      className="fixed inset-0 z-50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="coach-tour-title"
      aria-describedby="coach-tour-body"
    >
      {/* 영역 밖을 덮는 그림자. 덮개 자체가 클릭을 막는다 */}
      <div
        className="absolute rounded-3xl ring-2 ring-ice transition-all duration-300"
        style={
          box
            ? {
                top: box.top - PAD,
                left: box.left - PAD,
                width: box.width + PAD * 2,
                height: box.height + PAD * 2,
                boxShadow: "0 0 0 200vmax color-mix(in srgb, var(--color-night) 72%, transparent)",
              }
            : { inset: 0, background: "color-mix(in srgb, var(--color-night) 72%, transparent)" }
        }
      />
      <div
        className="absolute right-6 left-6 mx-auto flex max-w-[560px] animate-fade flex-col gap-3 rounded-3xl bg-white px-7 pt-6 pb-5 shadow-modal mirror:shadow-[inset_0_0_0_2px_var(--color-line-2)]"
        style={bubbleStyle}
      >
        <span className="font-label text-[14px] font-semibold tracking-[.16em] text-navy tabular">
          {index + 1} / {total}
        </span>
        <h2 id="coach-tour-title" className="font-display text-[26px] leading-[1.3] text-ink">
          {step.title}
        </h2>
        <p
          id="coach-tour-body"
          className="text-[18px] leading-[1.55] text-pretty whitespace-pre-line text-mute"
        >
          {step.body}
        </p>
        <div className="flex items-center justify-end gap-2.5 pt-2">
          {!last && (
            <PillButton variant="line" size="md" onClick={onDone} className="text-mute">
              건너뛰기
            </PillButton>
          )}
          <PillButton
            ref={next}
            variant="navy"
            size="md"
            onClick={() => (last ? onDone() : setIndex((i) => i + 1))}
          >
            {last ? "시작하기" : "다음"}
          </PillButton>
        </div>
      </div>
    </div>
  );
}
