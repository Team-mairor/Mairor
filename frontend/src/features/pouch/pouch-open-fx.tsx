/**
 * 내 파우치 진입 연출. 지퍼가 열리면서 제품 일러스트가 튀어나온 뒤 2.1초에 사라진다.
 * 프로토타입 pouchFxEl을 그대로 옮겼다.
 */
import { Illustration } from "./illustration";

const SPRING = "cubic-bezier(.34,1.56,.64,1)";
/** [종류, dx, dy, 회전, 폭] */
const ITEMS: [string, number, number, number, number][] = [
  ["립스틱", -150, -190, -14, 56],
  ["컴팩트", -20, -240, 6, 100],
  ["브러시", 120, -200, 12, 74],
  ["브로우 펜슬", 0, -130, -6, 56],
];
const CAT: Record<string, "립" | "치크" | "도구" | "브로우"> = {
  립스틱: "립",
  컴팩트: "치크",
  브러시: "도구",
  "브로우 펜슬": "브로우",
};

export function PouchOpenFx() {
  return (
    <div
      className="pointer-events-none absolute inset-0 z-[5] flex flex-col items-center justify-center gap-9 bg-white"
      style={{ animation: "mr-overlay-out 2100ms ease forwards" }}
      aria-hidden
    >
      <div className="relative mt-40 h-60 w-80" style={{ perspective: 700 }}>
        {ITEMS.map(([type, dx, dy, r, w], i) => (
          <div
            key={type}
            className="absolute top-[50px] z-[1] opacity-0"
            style={
              {
                left: 160 - w / 2,
                "--dx": `${dx}px`,
                "--dy": `${dy}px`,
                "--r": `${r}deg`,
                filter:
                  "drop-shadow(4px 0 0 #fff) drop-shadow(-4px 0 0 #fff) drop-shadow(0 4px 0 #fff) drop-shadow(0 -4px 0 #fff) drop-shadow(0 10px 14px rgba(58,14,37,.22))",
                animation: `mr-pop-out 700ms ${SPRING} ${820 + i * 110}ms forwards`,
              } as React.CSSProperties
            }
          >
            <Illustration item={{ cat: CAT[type], type }} color="#F4B6CF" width={w} />
          </div>
        ))}
        {/* 열리는 입구 */}
        <div
          className="absolute top-[52px] left-6 z-0 h-[26px] w-[272px] origin-left scale-x-0 rounded-full bg-[#2A0A1B]"
          style={{ animation: "mr-open-x 650ms cubic-bezier(.6,0,.3,1) 150ms forwards" }}
        />
        {/* 파우치 몸통 */}
        <div className="absolute top-[60px] left-0 z-[2] h-[190px] w-80 [filter:drop-shadow(0_22px_30px_rgba(58,14,37,.28))]">
          <div
            className="absolute inset-0 rounded-t-[26px] rounded-b-[54px]"
            style={{
              clipPath: "polygon(6% 0, 94% 0, 100% 100%, 0 100%)",
              background: "linear-gradient(160deg,#B3306F 0%,#991E5A 45%,#7E164A 100%)",
            }}
          >
            <div
              className="absolute inset-x-0 top-0 h-5 shadow-[inset_0_-2px_0_rgba(0,0,0,.15)]"
              style={{
                background: "repeating-linear-gradient(90deg,#E9DCE3 0 5px,#B89AAA 5px 8px)",
              }}
            />
            <div className="absolute top-8 right-[22px] bottom-[18px] left-[22px] rounded-t-[14px] rounded-b-[40px] border-2 border-dashed border-[rgba(239,192,218,.65)]" />
            <div className="absolute inset-x-0 top-[82px] mx-auto w-max rounded-[10px] bg-white px-4 py-1.5 font-serif text-[30px] text-plum italic shadow-[0_2px_0_rgba(0,0,0,.08)]">
              mairor
            </div>
          </div>
          {/* 지퍼 손잡이 */}
          <div
            className="absolute -top-2 left-[4%] z-[3] h-10 w-[26px]"
            style={{ animation: "mr-zip 650ms cubic-bezier(.6,0,.3,1) 150ms forwards" }}
          >
            <span className="absolute top-0 left-1 h-3.5 w-[18px] rounded border-2 border-white bg-line-3" />
            <span className="absolute top-3 left-[5px] h-[26px] w-4 rounded-t-md rounded-b-[10px] border-[3px] border-white bg-lime" />
          </div>
          {/* 고리 */}
          <div className="absolute top-10 -right-[26px] h-14 w-11 rounded-r-[26px] border-8 border-l-0 border-ink" />
        </div>
      </div>
      <span
        className="font-display text-[28px] text-ink opacity-0"
        style={{ animation: "mr-fade 500ms ease 500ms forwards" }}
      >
        내 파우치를 열어볼게요
      </span>
    </div>
  );
}
