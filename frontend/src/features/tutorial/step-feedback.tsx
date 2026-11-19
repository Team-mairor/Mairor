import { X } from "lucide-react";

/**
 * 묶음 사진 뒤 하단에 띄우는 단계 끝 안내 문장(최대 3줄). 준비 카드(z-[4])와 상단 바(z-[5]) 위에 떠서
 * 다음 묶음 준비 카드와 같이 읽힌다. 상자는 터치를 통과시켜 아래 「시작하기」를 가리지 않고,
 * 오른쪽 위 닫기 버튼만 눌린다. 점수 · 합격 · 숫자는 보이지 않는다
 */
export function StepFeedback({ lines, onDismiss }: { lines: string[]; onDismiss: () => void }) {
  if (!lines.length) return null;
  return (
    <div
      data-testid="step-feedback"
      className="pointer-events-none absolute inset-x-7 bottom-[18px] z-[6] flex animate-fade items-start gap-3 rounded-[24px] bg-night/90 py-5 pr-3 pl-6 text-white backdrop-blur-sm"
    >
      <div role="status" aria-live="polite" className="flex min-w-0 flex-1 flex-col gap-2">
        {lines.map((line) => (
          <span key={line} className="text-[20px] leading-[1.4] font-bold text-pretty">
            {line}
          </span>
        ))}
      </div>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="안내 닫기"
        className="pointer-events-auto -mt-2 flex size-11 shrink-0 items-center justify-center rounded-full hover:bg-white/15"
      >
        <X className="size-5" strokeWidth={2} aria-hidden />
      </button>
    </div>
  );
}
