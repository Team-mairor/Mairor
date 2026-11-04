/**
 * 얼굴이 아직 잡히지 않았을 때 원 안에 띄우는 예시. 선으로 그린 얼굴이 비스듬히 멀리 있다가
 * 다가오며 정면을 보는 동작을 되풀이해, 어떻게 맞추면 되는지 보여 준다.
 * 이목구비를 윤곽보다 앞(translateZ)에 두고 CSS 3D로 돌려 고개를 돌릴 때 입체감이 나게 한다.
 * 선은 navy라 일반 모드에서는 진하고, 미러필름 모드에서는 밝은 페리윙클로 보인다
 */
export function FaceDemo() {
  return (
    <div
      className="absolute inset-0 flex animate-fade items-center justify-center bg-cream/85"
      style={{ perspective: 900 }}
      aria-hidden
    >
      <div
        className="relative"
        style={{
          width: 250,
          height: 320,
          transformStyle: "preserve-3d",
          animation: "mr-face-turn 5.2s cubic-bezier(.45,0,.25,1) infinite",
        }}
      >
        {/* 윤곽. 정면을 볼 때 밝게 빛난다 */}
        <div
          className="absolute inset-0 rounded-[50%] border-[3px] border-navy"
          style={{ animation: "mr-face-glow 5.2s ease-in-out infinite" }}
        />
        {/* 이목구비 */}
        <div className="absolute inset-0" style={{ transform: "translateZ(48px)" }}>
          <span className="absolute top-[34%] left-[22%] h-[3px] w-[44px] -rotate-6 rounded-full bg-navy" />
          <span className="absolute top-[34%] right-[22%] h-[3px] w-[44px] rotate-6 rounded-full bg-navy" />
          <span className="absolute top-[42%] left-[25%] h-[12px] w-[34px] rounded-[50%] border-[3px] border-navy" />
          <span className="absolute top-[42%] right-[25%] h-[12px] w-[34px] rounded-[50%] border-[3px] border-navy" />
          <span className="absolute top-[48%] left-1/2 h-[46px] w-[3px] -translate-x-1/2 rounded-full bg-navy" />
          <span className="absolute top-[62%] left-1/2 h-[10px] w-[30px] -translate-x-1/2 rounded-b-full border-x-[3px] border-b-[3px] border-navy" />
          <span className="absolute top-[72%] left-1/2 h-[20px] w-[70px] -translate-x-1/2 rounded-b-full border-b-[3px] border-navy" />
        </div>
      </div>
    </div>
  );
}
