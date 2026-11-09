"use client";

import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { PillButton } from "@/components/ui/pill-button";
import { emptyDraft, PouchBoard, ProductSheet, type ProductDraft } from "@/features/pouch";
import { useSession } from "@/features/session";
import { HowItWorksSlide } from "@/features/tutorial";
import { cn } from "@/lib/utils";
import { DEFAULT_POUCH } from "@/mocks/mock-data";

/** 온보딩 4장: 기능 소개 3장 + 파우치 담기. 이 기기에서 최초 1회 (POUCH-001) */
export default function OnboardingPage() {
  const router = useRouter();
  const { state, update } = useSession();
  const [slide, setSlide] = useState(0); // 0~2 소개, 3 파우치
  const [newIds, setNewIds] = useState<string[]>([]);
  const [form, setForm] = useState<ProductDraft | null>(null);

  const mine = state.pouch.filter((p) => newIds.includes(p.id));
  const demo = mine.length === 0;
  // 아직 담은 제품이 없으면 샘플 제품을 흐리게 보여 준다 (예시일 뿐 파우치에 넣지 않는다)
  const items = demo ? DEFAULT_POUCH : mine;

  const finish = () => {
    update({ onboarded: true });
    router.replace("/home");
  };

  return (
    <main className="relative flex flex-1 flex-col bg-white">
      <div className="flex min-h-0 flex-1 items-center justify-center overflow-y-auto px-10 pt-7 pb-9">
        <div className="flex w-full max-w-[648px] flex-col">
          <Progress step={slide} onAuto={() => setSlide((s) => (s < 2 ? s + 1 : s))} />

          {slide < 3 ? (
            <>
              <HowItWorksSlide index={slide} />
              <div className="flex items-center gap-3 px-3 pt-7">
                {slide < 2 && (
                  <PillButton
                    variant="line"
                    size="cta"
                    onClick={() => setSlide(3)}
                    className="text-mute"
                  >
                    건너뛰기
                  </PillButton>
                )}
                <CtaButton onClick={() => setSlide((s) => s + 1)}>
                  {slide < 2 ? "다음" : "다음 · 내 파우치 채우기"}
                </CtaButton>
              </div>
            </>
          ) : (
            <>
              <PouchBoard
                items={items}
                dim={demo}
                animate
                scale={0.62}
                grid={36}
                slots="tall"
                className="h-[540px] rounded-[26px]"
                onEdit={(p) => setForm(demo ? emptyDraft() : { ...p })}
              >
                <span
                  className={cn(
                    "absolute top-[18px] left-[18px] z-[2] flex items-center gap-2 rounded-full px-3.5 py-2 text-[16px] font-bold tabular shadow-float",
                    demo ? "bg-ink text-white" : "bg-white text-ink",
                  )}
                >
                  <span className={cn("size-2 rounded-full", demo ? "bg-mint" : "bg-cyan")} />
                  {demo ? "예시 · 이렇게 담겨요" : `My pouch · ${mine.length}개`}
                </span>
                <div
                  className="absolute right-[5%] bottom-[7%] z-[6]"
                  style={{
                    animation: `mr-drop 760ms cubic-bezier(.2,.9,.25,1.15) ${350 + items.length * 240 + 120}ms both`,
                  }}
                >
                  <button
                    type="button"
                    onClick={() => setForm(emptyDraft())}
                    className="flex size-[200px] -rotate-[4deg] flex-col items-center justify-center gap-2 rounded-full border-4 border-dashed border-cyan bg-ice/5 text-navy hover:bg-ice/10"
                  >
                    <Plus className="size-12" strokeWidth={2.2} aria-hidden />
                    <span className="text-[28px] font-bold">제품 담기</span>
                  </button>
                </div>
              </PouchBoard>
              <div className="flex animate-fade flex-col gap-3 px-3 pt-7">
                <span className="font-label text-[14px] font-semibold tracking-[.16em] text-navy">
                  MY POUCH — 04
                </span>
                <h1 className="font-display text-[38px] leading-[1.2] text-pretty text-ink">
                  내 화장품을 파우치에 담아요
                </h1>
                <p className="text-[19px] leading-[1.55] text-pretty text-mute">
                  {demo
                    ? "아직 담긴 제품이 없어요. 가진 제품을 담아 두면 영상 속 제품과 비교해 바로 쓸 수 있는 것과 대체할 수 있는 것을 알려 드려요."
                    : `${mine.length}개 담았어요. 더 담거나, 지금 바로 시작해도 돼요.`}
                </p>
              </div>
              <div className="flex items-center gap-3 px-3 pt-7">
                <PillButton variant="line" size="cta" onClick={finish} className="text-mute">
                  나중에 할게요
                </PillButton>
                <CtaButton onClick={demo ? () => setForm(emptyDraft()) : finish}>
                  {demo ? "첫 화장품 담기" : `${mine.length}개 담고 시작하기`}
                </CtaButton>
              </div>
            </>
          )}
        </div>
      </div>

      {form && (
        <ProductSheet
          draft={form}
          onClose={() => setForm(null)}
          onSaved={(item, isNew) => isNew && setNewIds((ids) => [item.id, ...ids])}
        />
      )}
    </main>
  );
}

/** 4칸 스토리 진행 바. 현재 칸이 다 차면 onAuto (소개 3장은 5.6초 자동 넘김) */
function Progress({ step, onAuto }: { step: number; onAuto: () => void }) {
  return (
    <div className="flex items-center gap-5 px-3 pt-2 pb-5">
      <span className="font-label text-[13px] font-semibold tracking-[.16em] whitespace-nowrap text-mute">
        WELCOME TO MAIROR
      </span>
      <div className="grid flex-1 grid-cols-4 gap-1.5">
        {[0, 1, 2, 3].map((i) => (
          <span
            key={i}
            className={cn(
              "relative h-1 overflow-hidden rounded-full",
              i < step ? "bg-navy" : "bg-line",
            )}
          >
            {i === step && (
              <span
                key={step}
                className="absolute inset-0 origin-left bg-navy"
                style={{
                  animation:
                    step < 3
                      ? "mr-story 5.6s linear both"
                      : "mr-story 1.8s cubic-bezier(.2,.8,.2,1) both",
                }}
                onAnimationEnd={(e) => e.animationName === "mr-story" && step < 3 && onAuto()}
              />
            )}
          </span>
        ))}
      </div>
      <span className="font-serif text-[24px] leading-none whitespace-nowrap text-navy tabular">
        {String(step + 1).padStart(2, "0")}
        <span className="text-[16px] text-mute"> / 04</span>
      </span>
    </div>
  );
}

function CtaButton({ onClick, children }: { onClick: () => void; children: string }) {
  return (
    <PillButton size="cta" trailing onClick={onClick} className="min-w-0 flex-1">
      {children}
    </PillButton>
  );
}
