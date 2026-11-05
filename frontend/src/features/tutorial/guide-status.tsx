import { PillButton } from "@/components/ui/pill-button";

/** 가이드를 보여 줄 수 없을 때 튜토리얼 자리에 띄우는 안내 (불러오는 중·없음·실패·로그인 필요·빈 가이드) */
export function GuideStatus({
  title,
  body,
  action,
}: {
  title: string;
  body?: string;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-5 px-10 text-center">
      <h1 className="font-display text-[30px] leading-[1.25] text-white">{title}</h1>
      {body && <p className="max-w-[520px] text-[18px] leading-[1.5] text-line-2">{body}</p>}
      {action && (
        <PillButton size="cta" onClick={action.onClick}>
          {action.label}
        </PillButton>
      )}
    </main>
  );
}
