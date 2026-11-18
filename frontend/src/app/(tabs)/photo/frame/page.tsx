import { ChevronLeft } from "lucide-react";
import Link from "next/link";

import { PHOTO_FRAME_OPTIONS, type PhotoFrameOption } from "@/features/photo-booth";

/** 이미지가 없는 프레임은 칸 배치를 그려 보여 준다. 좌표는 프레임 출력 크기 대비 % */
function FramePreview({ frame }: { frame: PhotoFrameOption }) {
  const { output, slots, id } = frame.template;
  const name = `${frame.name} 프레임`;

  if (frame.previewSrc) {
    return (
      <>
        {/* eslint-disable-next-line @next/next/no-img-element -- 정적 예시 이미지, 최적화 불필요 */}
        <img src={frame.previewSrc} alt={name} className="block h-auto w-full mirror:hidden" />
        {/* eslint-disable-next-line @next/next/no-img-element -- 정적 예시 이미지, 최적화 불필요 */}
        <img
          src={frame.previewMirrorSrc ?? frame.previewSrc}
          alt={name}
          className="hidden h-auto w-full mirror:block"
        />
      </>
    );
  }

  return (
    <div
      role="img"
      aria-label={name}
      data-frame={id}
      className="relative w-full"
      style={{ aspectRatio: `${output.width}/${output.height}`, background: output.background }}
    >
      {slots.map((slot) => (
        <span
          key={slot.id}
          aria-hidden
          className="absolute"
          style={{
            left: `${(slot.x / output.width) * 100}%`,
            top: `${(slot.y / output.height) * 100}%`,
            width: `${(slot.width / output.width) * 100}%`,
            height: `${(slot.height / output.height) * 100}%`,
            background: frame.previewSlotColor,
          }}
        />
      ))}
    </div>
  );
}

/** 촬영 전에 네 컷 프레임을 고른다. 고른 프레임은 주소의 frame 값으로 촬영 화면에 넘긴다. */
export default function PhotoFramePage() {
  return (
    <main className="flex min-h-full flex-1 flex-col text-ink">
      <header className="flex h-28 shrink-0 items-center px-10">
        <Link
          href="/photo"
          aria-label="뒤로"
          className="flex size-[60px] items-center justify-center rounded-full border border-ink text-ink hover:bg-cream-2"
        >
          <ChevronLeft className="size-[22px]" strokeWidth={1.9} aria-hidden />
        </Link>
      </header>

      <section className="flex min-h-0 flex-1 flex-col justify-center gap-12 px-12 pb-16">
        <div className="flex flex-col gap-4">
          <span className="font-label text-[16px] font-semibold tracking-[.16em] text-navy mirror:text-[22px]">
            CHOOSE A FRAME
          </span>
          <h1 className="font-display text-[44px] leading-[1.25] text-ink">프레임을 골라 주세요</h1>
        </div>

        <ul className="grid grid-cols-3 gap-6">
          {PHOTO_FRAME_OPTIONS.map((frame) => (
            <li key={frame.id}>
              <Link
                href={`/photo/capture?frame=${frame.id}`}
                aria-label={`${frame.name} 프레임으로 촬영 시작`}
                className="group flex flex-col gap-4 text-center"
              >
                <span className="block overflow-hidden rounded-sm shadow-frame transition-transform group-active:scale-[.98]">
                  <FramePreview frame={frame} />
                </span>
                <span className="font-display text-[26px] text-ink">{frame.name}</span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
