"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Modal } from "@/components/ui/modal";
import { PillButton } from "@/components/ui/pill-button";
import { useHiddenVideo } from "@/features/face";
import { setPhotoConsent, useGuide, useRunQuery as useQuery } from "@/features/guide";
import { CameraErrorNote } from "@/features/live";
import { runHref, useSession } from "@/features/session";
import { HowItWorksSlide } from "@/features/tutorial";
import { errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * 09 튜토리얼 안내 · 사진 저장 동의. 리포트에 단계 사진이 꼭 남도록 동의해야 시작할 수 있다.
 * 안내 3장은 이 기기에서 처음 시작할 때만. ?review=1 이면 슬라이드만 보고 튜토리얼로 돌아간다. ?force=1 은 확인용.
 */
export default function TutorialGuidePage() {
  const router = useRouter();
  const query = useQuery();
  const { state, update, enterTutorial, isCurrentRun } = useSession();
  const { load, retry } = useGuide();
  const run = state.run;
  const n = run.mode === "guide" && load.status === "ready" ? load.guide.steps.length : 0;
  const consentRows = [
    ["저장 항목", `스텝별 얼굴 사진 (최대 ${n}장)`],
    ["쓰는 곳", "내 리포트의 과정 사진 · 비교"],
    ["삭제", "리포트를 지우면 사진도 함께 지워져요"],
  ];
  const href = (path: string) => runHref(path, run.guideId);
  const review = query?.get("review") === "1";
  const [slide, setSlide] = useState(0); // 0~2 안내, 3 동의
  const showSlides = review || query?.get("force") === "1" || !state.tutSeen;
  const phase = showSlides ? slide : 3;
  useHiddenVideo();

  useEffect(() => {
    if (run.mode !== "guide") router.replace("/select");
  }, [router, run.mode]);

  const endSlides = () => {
    if (review) return router.push(href("/tutorial"));
    update({ tutSeen: true });
    setSlide(3);
  };
  const consenting = useRef(false);
  /** 동의를 서버에 저장하지 못한 이유. 버튼을 다시 누를 수 있다 */
  const [consentError, setConsentError] = useState<string | null>(null);
  // 사진 저장에 동의해야 시작할 수 있어 늘 동의로 저장한다
  const consent = async () => {
    if (consenting.current) return;
    consenting.current = true;
    setConsentError(null);
    try {
      if (!(await retry())) return;
      // 실제 가이드는 동의 여부를 서버 실행에 저장한다
      if (!run.executionId) {
        setConsentError("실행 정보가 없어요. 제품 확인에서 다시 시작해 주세요.");
        return;
      }
      await setPhotoConsent(run.executionId, true);
      if (!isCurrentRun(run.id)) return;
      enterTutorial(run.id, true);
      router.push(href("/tutorial"));
    } catch (e) {
      setConsentError(errorMessage(e));
    } finally {
      consenting.current = false;
    }
  };

  if (!query || run.mode !== "guide") return null;

  return (
    <main className="relative flex flex-1 flex-col">
      <CameraErrorNote className="z-[6]" />
      <Modal
        open
        label="튜토리얼 안내"
        overlayClassName="z-[5] px-[60px] py-8 backdrop-blur-sm"
        className="relative flex max-w-[680px] flex-col rounded-[36px] px-4 pt-[18px] pb-6 text-ink"
      >
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
                      i < phase ? "bg-navy" : "bg-line",
                    )}
                  >
                    {i === phase && (
                      <span
                        key={phase}
                        className="absolute inset-0 origin-left bg-navy"
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
              <span className="font-serif text-[24px] leading-none whitespace-nowrap text-navy tabular">
                {String(phase + 1).padStart(2, "0")}
                <span className="text-[16px] text-mute"> / 03</span>
              </span>
            </div>
            <HowItWorksSlide index={phase} />
            <div className="flex items-center gap-3 px-3 pt-7">
              {phase < 2 && (
                <PillButton variant="line" size="cta" onClick={endSlides} className="text-mute">
                  건너뛰기
                </PillButton>
              )}
              <PillButton
                size="cta"
                trailing
                onClick={() => (phase < 2 ? setSlide(phase + 1) : endSlides())}
                className="min-w-0 flex-1"
              >
                {phase < 2 ? "다음" : review ? "튜토리얼로 돌아가기" : "시작하기"}
              </PillButton>
            </div>
          </>
        ) : (
          <div className="flex animate-fade flex-col gap-6 px-4 pt-4 pb-1">
            <span className="font-label text-[13px] font-semibold tracking-[.16em] text-mute">
              BEFORE YOU START
            </span>
            <div className="flex flex-col gap-3">
              <h1 className="font-display text-[34px] leading-[1.25]">
                단계 사진 저장에 동의해 주세요
              </h1>
              <p className="text-[19px] leading-[1.55] text-pretty text-mute">
                스텝을 마칠 때마다 얼굴을 찍어 리포트에 과정을 남겨요. 사진 저장에 동의해야
                튜토리얼을 시작할 수 있어요.
              </p>
            </div>
            <div className="flex flex-col rounded-[22px] border border-line">
              {consentRows.map(([k, v], i) => (
                <div
                  key={k}
                  className={cn(
                    "grid grid-cols-[120px_minmax(0,1fr)] gap-4 px-5 py-4",
                    i && "border-t border-line",
                  )}
                >
                  <span className="text-[17px] font-bold text-navy">{k}</span>
                  <span className="text-[17px] leading-[1.5] text-pretty">{v}</span>
                </div>
              ))}
            </div>
            <span className="text-[15px] leading-[1.5] text-pretty text-mute">
              얼굴 등록 사진은 이번 메이크업의 조명 기준으로만 쓰여요. 단계 사진 저장 여부와는
              관계없어요.
            </span>
            {consentError && (
              <p role="alert" className="text-[17px] leading-[1.5] text-error">
                {consentError}
              </p>
            )}
            <div className="flex gap-3">
              <PillButton
                variant="line"
                size="cta"
                onClick={() => router.push(href("/check"))}
                className="flex-1"
              >
                돌아가기
              </PillButton>
              <PillButton size="cta" onClick={consent} className="flex-1">
                동의하고 시작
              </PillButton>
            </div>
          </div>
        )}
      </Modal>
    </main>
  );
}
