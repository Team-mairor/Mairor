import Link from "next/link";

const STEPS = ["프레임 고르기", "네 장 연속 촬영", "다시 찍고 바로 저장"];

/** 메이크업 실행과 독립된 오늘네컷 진입 화면. 색·글꼴은 홈 대시보드 카드와 맞춘다. */
export default function PhotoBoothPage() {
  return (
    <main className="flex min-h-full flex-1 flex-col justify-center gap-16 py-10 text-ink">
      <section className="grid grid-cols-[minmax(0,1fr)_380px] items-center gap-10 px-10">
        <div className="flex flex-col gap-8">
          <div className="flex flex-col gap-4">
            <span className="font-label text-[16px] font-semibold tracking-[.16em] text-navy mirror:text-[22px]">
              FOUR CUTS
            </span>
            <h1 className="font-display text-[52px] leading-[1.25] text-ink">
              오늘의 순간을
              <br />네 컷으로
            </h1>
          </div>

          <ol className="flex flex-col">
            {STEPS.map((step, index) => (
              <li
                key={step}
                className="flex h-21 items-center gap-[22px] border-t-2 border-line-3 text-[28px] font-bold last:border-b-2"
              >
                <span className="w-10 font-serif text-[34px] text-cyan italic mirror:font-label mirror:text-[30px] mirror:font-bold mirror:not-italic">
                  0{index + 1}
                </span>
                {step}
              </li>
            ))}
          </ol>
        </div>

        {/* 일반 모드는 검은 프레임, 미러필름 모드는 밝은(#f4f9ff) 프레임 예시를 보여 준다 */}
        <div className="w-[380px] rotate-2 rounded-sm shadow-float">
          {/* eslint-disable-next-line @next/next/no-img-element -- 정적 예시 이미지, 최적화 불필요 */}
          <img
            src="/images/photo/ssafy-final-frame.png"
            alt="SSAFY 15기 기념 네컷 프레임"
            className="block h-auto w-full mirror:hidden"
          />
          {/* eslint-disable-next-line @next/next/no-img-element -- 정적 예시 이미지, 최적화 불필요 */}
          <img
            src="/images/photo/ssafy-final-frame-mirror.png"
            alt="SSAFY 15기 기념 네컷 프레임"
            className="hidden h-auto w-full mirror:block"
          />
        </div>
      </section>

      {/* 위쪽 소개는 가운데 자리를 지키고 버튼만 내린다(translate는 배치 계산에 영향 없음) */}
      <div className="flex shrink-0 translate-y-16 justify-center px-10">
        {/* 위아래 가는 줄 사이에 세리프 이탤릭 부제와 제목. 바탕은 칠하지 않는다 */}
        <Link
          href="/photo/frame"
          className="flex h-28 w-[440px] flex-col items-center justify-center gap-2 border-y-2 border-navy text-navy transition-colors hover:bg-cream-2 active:scale-[.99]"
        >
          <span className="font-serif text-[24px] leading-none tracking-[.06em] italic mirror:text-[30px]">
            — Take four cuts —
          </span>
          <span className="font-display text-[32px] leading-none">촬영 시작</span>
        </Link>
      </div>
    </main>
  );
}
