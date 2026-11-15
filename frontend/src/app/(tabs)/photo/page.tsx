import { Camera } from "lucide-react";
import Link from "next/link";

import { BASIC_PHOTO_FRAME } from "@/features/photo-booth";

/** 메이크업 실행과 독립된 네컷 사진 진입 화면. */
export default function PhotoBoothPage() {
  return (
    <main className="flex min-h-0 flex-1 flex-col px-8 pt-8 pb-10">
      <header className="flex items-center justify-end">
        <span className="font-label text-[14px] font-semibold tracking-[.16em] text-mute">
          PHOTO BOOTH
        </span>
      </header>

      <section className="mx-auto flex w-full max-w-[620px] flex-1 flex-col justify-center gap-7 py-8">
        <div className="flex flex-col gap-3">
          <p className="font-label text-[15px] font-semibold tracking-[.14em] text-navy">
            JUST FOR FUN
          </p>
          <h1 className="font-display text-[36px] leading-[1.25] text-ink">
            오늘의 순간을 네 컷으로
          </h1>
          <p className="text-[18px] leading-[1.6] text-mute">
            메이크업 가이드를 시작하지 않아도 사진을 찍고 네 컷으로 꾸밀 수 있어요.
          </p>
        </div>

        <div className="flex items-center gap-7 rounded-3xl border border-line bg-white p-6">
          <div
            className="grid aspect-[2/3] w-[132px] shrink-0 grid-cols-2 gap-1.5 p-2"
            style={{ backgroundColor: BASIC_PHOTO_FRAME.output.background }}
            aria-label="네 장 사진이 들어가는 기본 프레임 미리보기"
            role="img"
          >
            {BASIC_PHOTO_FRAME.slots.map((slot) => (
              <span key={slot.id} className="rounded-sm bg-ice" />
            ))}
          </div>
          <div className="flex min-w-0 flex-col gap-2">
            <span className="font-display text-[24px] text-ink">기본 네 컷</span>
            <span className="text-[16px] leading-[1.5] text-mute">
              네 장을 차례로 촬영하고, 마음에 들지 않는 컷은 다시 찍거나 사진별 위치와 확대를 조정할
              수 있어요.
            </span>
            <span className="mt-1 text-[14px] text-mute-2">
              지금은 기능 확인용 기본 프레임을 사용해요.
            </span>
          </div>
        </div>

        <Link
          href="/photo/capture"
          className="flex h-16 items-center justify-center gap-2 rounded-full bg-navy text-[18px] font-bold text-white"
        >
          <Camera className="size-5" aria-hidden />
          촬영 시작
        </Link>
      </section>
    </main>
  );
}
