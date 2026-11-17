import { PillButton } from "@/components/ui/pill-button";
import { RoundBack } from "@/features/live";

interface Action {
  label: string;
  disabled: boolean;
  onClick: () => void;
}

/** 튜토리얼 하단 버튼 줄. 왼쪽은 이전·촬영 취소, 오른쪽은 다음으로 넘어가는 큰 버튼 */
export function StepActions({ back, next }: { back: Action; next: Action }) {
  return (
    <div className="flex items-center gap-3">
      <RoundBack onClick={back.onClick} label={back.label} disabled={back.disabled} />
      <PillButton
        size="cta"
        trailing
        onClick={next.onClick}
        disabled={next.disabled}
        className="min-w-0 flex-1"
      >
        {next.label}
      </PillButton>
    </div>
  );
}
