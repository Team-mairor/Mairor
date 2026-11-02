"use client";

import { ArrowRight } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { CameraErrorNote } from "@/features/live/live-chrome";
import { useSession } from "@/features/session";
import { HowItWorksSlide } from "@/features/tutorial/how-it-works";
import { GUIDE_STEPS } from "@/lib/mock-data";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";

const CONSENT_ROWS: [string, string][] = [
  ["저장 항목", `스텝별 얼굴 사진 (최대 ${GUIDE_STEPS.length}장)`],
  ["쓰는 곳", "내 리포트의 과정 사진 · 비교"],
  ["삭제", "리포트를 지우면 사진도 함께 지워져요"],
];

/**
 * 09 튜토리얼 안내 · 사진 저장 동의 (GUIDE-002).
 * 안내 3장은 이 기기에서 처음 시작할 때만. ?review=1 이면 슬라이드만 보고 튜토리얼로 돌아간다. ?force=1 은 확인용.
 */
export default function TutorialGuidePage() {
  const router = useRouter();
  const query = useQuery();
  const { state, update, updateRun } = useSession();
  const review = query?.get("review") === "1";
  const [slide, setSlide] = useState(0); // 0~2 안내, 3 동의
  const showSlides = review || query?.get("force") === "1" || !state.tutSeen;
  const phase = showSlides ? slide : 3;

  const endSlides = () => {
    if (review) return router.push("/tutorial");
    update({ tutSeen: true });
    setSlide(3);
  };
  const consent = (ok: boolean) => {
    updateRun({ photoOk: ok, captures: [] });
    router.push("/tutorial");
  };

  return (
    <main className="relative flex flex-1 flex-col">
      <CameraErrorNote className="z-[6]" />
      <div className="absolute inset-0 z-[5] flex animate-fade items-center justify-center bg-[rgba(11,20,48,.58)] px-[60px] py-8 backdrop-blur-sm">
        <div className="relative flex w-full max-w-[680px] flex-col rounded-[36px] bg-white px-4 pt-[18px] pb-6 text-ink shadow-[0_40px_80px_rgba(6,10,26,.4)]">
          {phase < 3 ? (
            <>
              <div className="flex items-center gap-5 px-3 pt-2 pb-5">
                <span className="font-label text-[13px] font-semibold tracking-[.16em] whitespace-nowrap text-mute">
                  TUTORIAL GUIDE
                </span>
                <div className="grid flex-1 grid-cols-3 gap-1.5">
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className={cn(
                        "relative h-1 overflow-hidden rounded-full",
                        i < phase ? "bg-plum" : "bg-line",
                      )}
                    >
                      {i === phase && (
                        <span
                          key={phase}
                          className="absolute inset-0 origin-left bg-plum"
                          style={{ animation: "mr-story 5.6s linear both" }}
                          onAnimationEnd={(e) =>
                            e.animationName === "mr-story" &&
                            (phase < 2 ? setSlide(phase + 1) : endSlides())
                          }
                        />
                      )}
                    </span>
                  ))}
                </div>
                <span className="font-serif text-[24px] leading-none whitespace-nowrap text-plum tabular">
                  {String(phase + 1).padStart(2, "0")}
                  <span className="text-[16px] text-mute"> / 03</span>
                </span>
              </div>
              <HowItWorksSlide index={phase} />
              <div className="flex items-center gap-3 px-3 pt-7">
                {phase < 2 && (
                  <button
                    type="button"
                    onClick={endSlides}
                    className="flex h-[72px] shrink-0 items-center justify-center rounded-full border-[1.5px] border-line-2 px-[30px] text-[20px] font-semibold whitespace-nowrap text-mute hover:bg-cream active:scale-[.97]"
                  >
                    건너뛰기
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => (phase < 2 ? setSlide(phase + 1) : endSlides())}
                  className="flex h-[72px] min-w-0 flex-1 items-center justify-between gap-4 rounded-full bg-pink py-0 pr-2.5 pl-[30px] text-white active:scale-[.98]"
                >
                  <span className="truncate text-[21px] font-bold">
                    {phase < 2 ? "다음" : review ? "튜토리얼로 돌아가기" : "시작하기"}
                  </span>
                  <span className="flex size-[52px] shrink-0 items-center justify-center rounded-full bg-white text-pink">
                    <ArrowRight className="size-6" strokeWidth={2.4} aria-hidden />
                  </span>
                </button>
              </div>
            </>
          ) : (
            <div className="flex animate-fade flex-col gap-6 px-4 pt-4 pb-1">
              <span className="font-label text-[13px] font-semibold tracking-[.16em] text-mute">
                BEFORE YOU START
              </span>
              <div className="flex flex-col gap-3">
                <h1 className="font-display text-[34px] leading-[1.25]">단계 사진을 저장할까요?</h1>
                <p className="text-[19px] leading-[1.55] text-pretty text-mute">
                  저장하면 스텝을 마칠 때마다 얼굴을 찍어 리포트에 과정을 남겨요. 저장하지 않아도
                  튜토리얼은 똑같이 진행돼요.
                </p>
              </div>
              <div className="flex flex-col rounded-[22px] border border-line">
                {CONSENT_ROWS.map(([k, v], i) => (
                  <div
                    key={k}
                    className={cn(
                      "grid grid-cols-[120px_minmax(0,1fr)] gap-4 px-5 py-4",
                      i && "border-t border-line",
                    )}
                  >
                    <span className="text-[17px] font-bold text-plum">{k}</span>
                    <span className="text-[17px] leading-[1.5] text-pretty">{v}</span>
                  </div>
                ))}
              </div>
              <span className="text-[15px] leading-[1.5] text-pretty text-mute">
                얼굴 등록 사진은 이번 메이크업의 조명 기준으로만 쓰여요. 단계 사진 저장 여부와는
                관계없어요.
              </span>
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => consent(false)}
                  className="flex h-[72px] flex-1 items-center justify-center rounded-full border-[1.5px] border-line-2 text-[20px] font-bold whitespace-nowrap hover:bg-cream active:scale-[.97]"
                >
                  사진 없이 시작
                </button>
                <button
                  type="button"
                  onClick={() => consent(true)}
                  className="flex h-[72px] flex-1 items-center justify-center rounded-full bg-pink text-[20px] font-bold whitespace-nowrap text-white active:scale-[.98]"
                >
                  사진 저장하고 시작
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
