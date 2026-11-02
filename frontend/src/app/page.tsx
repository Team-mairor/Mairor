"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";

import { Stage } from "@/components/stage";
import { useSession } from "@/features/session";

// 로고 점 패턴 (5×7)
const GLYPHS: Record<string, string[]> = {
  m: ["00000", "00000", "11010", "10101", "10101", "10001", "10001"],
  a: ["00000", "00000", "01110", "00001", "01111", "10001", "01111"],
  i: ["00100", "00000", "01100", "00100", "00100", "00100", "01110"],
  r: ["00000", "00000", "10110", "11001", "10000", "10000", "10000"],
  o: ["00000", "00000", "01110", "10001", "10001", "10001", "01110"],
};
const WORD = "mairor";
const CELL = 18;
const DOT = 13;
const EASE = "cubic-bezier(.2,.8,.2,1)";
const SPRING = "cubic-bezier(.34,1.56,.64,1)";
/** 점 연출이 끝나고 글자가 올라오는 시점(ms) */
const T = 1900;
/** 자동 이동 시점(ms) */
const AUTO_MS = T + 3600;

const LABELS: [x: number, y: number, label: string, side: "left" | "right", delay: number][] = [
  [190 + 147, 384 + 178, "BLUSH · CORAL", "left", T + 2350],
  [190 + 185, 384 + 287, "LIP · ROSE MLBB", "right", T + 2550],
  [190 + 276, 384 + 225, "BLUSH · PEACH", "right", T + 2450],
];

/** 00 인트로. 약 6초 뒤 또는 탭하면 로그인 상태에 따라 홈·로그인으로 간다 (USERS-003) */
export default function IntroPage() {
  const router = useRouter();
  const { state, hydrated } = useSession();

  const dots = useMemo(() => {
    const out: {
      key: string;
      x: number;
      y: number;
      on: boolean;
      d1: number;
      d2: number;
      seed: number;
    }[] = [];
    WORD.split("").forEach((ch, li) => {
      GLYPHS[ch].forEach((row, ry) =>
        row.split("").forEach((b, rx) => {
          const x = li * 6 * CELL + rx * CELL;
          const y = ry * CELL;
          const seed = (((li * 37 + ry * 13 + rx * 7) * 9301 + 49297) % 233280) / 233280;
          out.push({
            key: `${li}-${ry}-${rx}`,
            x,
            y,
            on: b === "1",
            d1: 350 + seed * 900,
            d2: 1750 + (x / 630) * 350,
            seed,
          });
        }),
      );
    });
    return out;
  }, []);

  // 저장된 세션을 읽기 전에는 loggedIn이 기본값(false)이라 탭해도 기다린다
  const next = () => {
    if (!hydrated) return;
    if (state.loggedIn) router.replace("/home");
    else router.replace(state.sessionExpired ? "/login?expired=basic" : "/login");
  };

  useEffect(() => {
    if (!hydrated) return;
    const t = setTimeout(next, AUTO_MS);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 타이머는 한 번만 건다
  }, [hydrated]);

  return (
    <main className="flex flex-1 flex-col bg-white" onClick={next}>
      <Stage className="cursor-pointer">
        <div
          className="absolute inset-x-0 top-[430px] h-[230px]"
          style={{ animation: `mr-up 1000ms cubic-bezier(.7,0,.2,1) ${T + 700}ms forwards` }}
        >
          <div className="absolute top-10 left-1/2 -ml-[315px] h-[126px] w-[630px]">
            {dots.map((d) => (
              <span
                key={d.key}
                className="absolute rounded-full opacity-0"
                style={{
                  left: d.x,
                  top: d.y,
                  width: DOT,
                  height: DOT,
                  background: d.on ? "#991E5A" : "#EFE4EA",
                  animation: d.on
                    ? `mr-dot 420ms ${SPRING} ${d.d1}ms forwards, mr-dot-out 380ms ease-in ${d.d2}ms forwards`
                    : `mr-fade 300ms ease ${250 + d.seed * 300}ms forwards, mr-dot-out 380ms ease-in ${d.d2}ms forwards`,
                }}
              />
            ))}
          </div>
          <div className="absolute inset-x-0 top-0 flex flex-col items-center">
            <span
              className="mb-3.5 font-label text-[12px] font-semibold tracking-[.24em] text-mute opacity-0"
              style={{ animation: `mr-fade 600ms ${EASE} ${T + 200}ms forwards` }}
            >
              N°01 — AI MAKEUP MIRROR
            </span>
            <div
              className="flex font-serif text-[168px] leading-none tracking-[-.03em] text-plum italic"
              aria-label="mairor"
            >
              {WORD.split("").map((ch, i) => (
                <span
                  key={i}
                  className="inline-block opacity-0"
                  style={{ animation: `mr-rise 800ms ${EASE} ${T + 60 + i * 70}ms forwards` }}
                >
                  {ch}
                </span>
              ))}
            </div>
            <div
              className="mt-1 h-[1.5px] w-[480px] origin-center scale-x-0 bg-plum"
              style={{ animation: `mr-line 800ms ${EASE} ${T + 500}ms forwards` }}
            />
          </div>
        </div>

        <div
          className="absolute top-[384px] left-[190px] h-[540px] w-[420px] bg-white"
          style={{
            clipPath: "inset(100% 0 0 0 round 210px 210px 28px 28px)",
            animation: `mr-wipe 1100ms cubic-bezier(.7,0,.2,1) ${T + 900}ms forwards`,
          }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element -- 고정 크기 연출 이미지 */}
          <img
            src="/images/login-editorial.png"
            alt=""
            className="absolute inset-0 h-full w-full object-cover object-[50%_30%]"
            style={{
              transform: "scale(1.18)",
              animation: `mr-zoom 1600ms ${EASE} ${T + 900}ms forwards`,
            }}
          />
          <div
            className="absolute inset-x-0 top-0 h-0.5 bg-pink opacity-0 shadow-[0_0_0_1px_rgba(255,255,255,.6)]"
            style={{ animation: `mr-scan 1200ms cubic-bezier(.45,0,.55,1) ${T + 1700}ms forwards` }}
          />
        </div>

        {LABELS.map(([x, y, label, side, d]) => (
          <div
            key={label}
            className="absolute size-0 opacity-0"
            style={{ left: x, top: y, animation: `mr-fade 400ms ${EASE} ${d}ms forwards` }}
          >
            <span
              className="absolute -top-[7px] -left-[7px] size-3.5 rounded-full bg-pink"
              style={{ animation: `mr-pulse 1400ms ease-out ${d}ms infinite` }}
            />
            <span className="absolute -top-[7px] -left-[7px] size-3.5 rounded-full bg-pink shadow-[0_0_0_3px_#fff]" />
            <span
              className={`absolute -top-3.5 flex h-7 items-center rounded-full bg-white px-3 font-label text-[11px] font-semibold tracking-[.12em] whitespace-nowrap text-ink ${side === "left" ? "right-4" : "left-4"}`}
            >
              {label}
            </span>
          </div>
        ))}

        <div className="absolute inset-x-0 top-[956px] flex flex-col items-center gap-2">
          <span
            className="font-serif text-[32px] text-ink italic opacity-0"
            style={{ animation: `mr-fade 700ms ${EASE} ${T + 1700}ms forwards` }}
          >
            Your mirror, your makeup artist.
          </span>
          <span
            className="font-display text-[20px] text-ink opacity-0"
            style={{ animation: `mr-fade 700ms ${EASE} ${T + 1900}ms forwards` }}
          >
            따라 하고 싶은 메이크업을 내 얼굴 위에 그대로
          </span>
        </div>

        <div
          className="absolute bottom-[90px] left-1/2 -ml-20 flex w-40 flex-col items-center gap-3 opacity-0"
          style={{ animation: `mr-fade 500ms ease ${T + 1900}ms forwards` }}
        >
          <div className="h-[3px] w-40 overflow-hidden rounded-full bg-line">
            <div
              className="h-full w-full origin-left scale-x-0 bg-pink"
              style={{ animation: `mr-bar 1700ms linear ${T + 1900}ms forwards` }}
            />
          </div>
          <span className="text-[13px] text-mute">탭하면 바로 시작해요</span>
        </div>

        <div className="pointer-events-none absolute inset-0 grid grid-cols-3 gap-0.5">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="bg-ink"
              style={{
                animation: `${i === 1 ? "mr-panel-down" : "mr-panel-up"} 820ms cubic-bezier(.7,0,.2,1) ${120 + i * 110}ms forwards`,
              }}
            />
          ))}
        </div>
      </Stage>
    </main>
  );
}
