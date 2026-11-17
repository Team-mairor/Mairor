/**
 * 기능 소개 3장. 온보딩(02-1)과 튜토리얼 안내(09)가 같은 내용을 쓴다.
 * 1 영역 표시 · 2 진하기 게이지 · 3 스텝 캡처
 */
const FACE = "/images/how-it-works-face.png";

/** 캡처 썸네일 7장: 얼굴 전체에서 눈 · 볼 · 입으로 좁혀 가는 확대 위치(왼쪽 · 위 여백 %, 사진 너비 %) */
const THUMBS: [ml: number, mt: number, w: number][] = [
  [-50, -30, 175],
  [-73, -36, 220],
  [-231, -99, 420],
  [-139, -102, 420],
  [-234, -143, 400],
  [-184, -218, 420],
  [-96, -97, 260],
];

const COPY = [
  {
    eyebrow: "HOW IT WORKS — 01",
    title: "내 얼굴에 맞춰 영역을 그려요",
    desc: "얼굴을 실시간으로 따라가며, 영상 속 메이크업 영역을 내 얼굴 위에 점선으로 그려 드려요.",
  },
  {
    eyebrow: "HOW IT WORKS — 02",
    title: "진하기를 실시간으로 비교해요",
    desc: "레퍼런스와 비교한 진하기를 게이지로 보여 줘요. 바르면서 직접 비교해 보세요.",
  },
  {
    eyebrow: "HOW IT WORKS — 03",
    title: "스텝마다 캡처, 끝나면 리포트",
    desc: "사진 저장에 동의하면 스텝마다 얼굴을 남겨요. 모든 스텝을 마치면 과정이 담긴 메이크업 리포트가 만들어져요.",
  },
];

/* eslint-disable @next/next/no-img-element -- 고정 좌표 연출 이미지 */
export function HowItWorksSlide({ index }: { index: number }) {
  const copy = COPY[index] ?? COPY[0];
  return (
    <div className="flex flex-col">
      <div className="relative h-[540px] overflow-hidden rounded-[26px] bg-line">
        <img src={FACE} alt="" className="absolute inset-0 size-full object-cover" />
        {index === 0 && (
          <div
            className="absolute rounded-full shadow-[0_0_0_1600px_color-mix(in_srgb,var(--color-night)_36%,transparent)]"
            style={{
              left: "54.3%",
              top: 210,
              width: "26%",
              height: 80,
              animation: "mr-spot 6.4s cubic-bezier(.65,0,.35,1) infinite",
            }}
          >
            <div className="absolute inset-0 rounded-full border-2 border-white" />
            <div
              className="absolute -inset-0.5 rounded-full border-2 border-white"
              style={{ animation: "mr-halo 1.6s cubic-bezier(.2,.8,.2,1) infinite" }}
            />
            <span className="absolute top-[calc(100%+12px)] left-1/2 flex -translate-x-1/2 items-center gap-2 rounded-full bg-white px-3.5 py-2 text-[16px] font-bold whitespace-nowrap text-ink shadow-float">
              <span className="size-2 rounded-full bg-cyan" />
              여기에 발라요
            </span>
          </div>
        )}
        {index === 1 && (
          <>
            <div
              className="absolute rounded-full"
              style={{
                left: "58%",
                top: 245,
                width: "26%",
                height: 150,
                background: "radial-gradient(closest-side,rgba(226,84,112,.62),rgba(226,84,112,0))",
                animation: "mr-blush 5.6s cubic-bezier(.4,0,.2,1) infinite",
              }}
            />
            <div
              className="absolute rounded-full shadow-[0_0_0_1600px_color-mix(in_srgb,var(--color-night)_30%,transparent)]"
              style={{ left: "60.6%", top: 261, width: "20.9%", height: 118 }}
            >
              <div className="absolute inset-0 rounded-full border-2 border-white" />
            </div>
            <div className="absolute inset-x-[18px] bottom-[18px] flex flex-col gap-3 rounded-[20px] bg-white/95 px-5 pt-4 pb-[18px] shadow-float">
              <div className="flex items-center justify-between">
                <span className="text-[16px] font-semibold text-mute">진하기 · 레퍼런스 대비</span>
                <span className="font-label text-[13px] font-semibold tracking-[.14em] text-navy">
                  LIVE
                </span>
              </div>
              <div className="relative h-6">
                <div className="absolute inset-x-0 top-[7px] h-2.5 overflow-hidden rounded-full bg-line">
                  <div
                    className="absolute top-0 bottom-0 left-0 rounded-full bg-cyan"
                    style={{ animation: "mr-gdemo 5.6s cubic-bezier(.4,0,.2,1) infinite" }}
                  />
                  <div className="absolute top-0 bottom-0 left-[52%] w-[3px] bg-ink" />
                </div>
                <span
                  className="absolute top-px size-[22px] rounded-full border-[3px] border-cyan bg-white shadow-float"
                  style={{ animation: "mr-gthumb 5.6s cubic-bezier(.4,0,.2,1) infinite" }}
                />
              </div>
            </div>
          </>
        )}
        {index === 2 && (
          <>
            <div className="absolute inset-x-8 top-16 bottom-[136px]">
              <span className="absolute top-0 left-0 size-10 rounded-tl-[14px] border-t-[3px] border-l-[3px] border-white" />
              <span className="absolute top-0 right-0 size-10 rounded-tr-[14px] border-t-[3px] border-r-[3px] border-white" />
              <span className="absolute bottom-0 left-0 size-10 rounded-bl-[14px] border-b-[3px] border-l-[3px] border-white" />
              <span className="absolute right-0 bottom-0 size-10 rounded-br-[14px] border-r-[3px] border-b-[3px] border-white" />
              <span className="absolute top-4 left-1/2 flex -translate-x-1/2 items-center gap-2 rounded-full bg-white/95 px-3.5 py-[7px] font-label text-[13px] font-semibold tracking-[.14em] whitespace-nowrap text-ink">
                <span className="size-2 rounded-full bg-cyan" />
                STEP CAPTURE
              </span>
            </div>
            <div
              className="absolute inset-0 bg-white opacity-0"
              style={{ animation: "mr-flash 520ms 400ms linear 7 both" }}
            />
            <div className="absolute inset-x-4 bottom-5 grid grid-cols-7 gap-[7px]">
              {THUMBS.map(([ml, mt, w], i) => (
                <div
                  key={i}
                  className="relative aspect-square overflow-hidden rounded-[14px] border-[3px] border-white bg-line shadow-float"
                  style={{
                    animation: `mr-thumb-in 460ms ${(0.4 + i * 0.52).toFixed(2)}s cubic-bezier(.2,.8,.2,1) both`,
                  }}
                >
                  <img
                    src={FACE}
                    alt=""
                    className="absolute top-0 h-auto max-w-none"
                    style={{ left: `${ml}%`, marginTop: `${mt}%`, width: `${w}%` }}
                  />
                </div>
              ))}
            </div>
          </>
        )}
      </div>
      <div className="flex animate-fade flex-col gap-3 px-3 pt-7" key={index}>
        <span className="font-label text-[14px] font-semibold tracking-[.16em] text-navy">
          {copy.eyebrow}
        </span>
        <h1 className="font-display text-[38px] leading-[1.2] text-pretty text-ink">
          {copy.title}
        </h1>
        <p className="text-[19px] leading-[1.55] text-pretty text-mute">{copy.desc}</p>
      </div>
    </div>
  );
}
