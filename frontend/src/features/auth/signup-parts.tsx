import { Check } from "lucide-react";

import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

/** 비밀번호 규칙 한 줄. 지켰으면 강조색으로 보인다 */
export function RuleItem({ ok, children }: { ok: boolean; children: string }) {
  return (
    <span className={cn("flex items-center gap-1.5", ok ? "text-navy" : "text-ash-2")}>
      <Check className="size-3.5" strokeWidth={3} aria-hidden />
      {children}
    </span>
  );
}

/** 입력 칸 옆에 놓는 확인·중복 확인 같은 보조 버튼 */
export function SideButton({
  tone,
  busy,
  children,
  ...props
}: React.ComponentProps<"button"> & { tone: "done" | "on" | "off"; busy?: boolean }) {
  return (
    <button
      type="button"
      {...props}
      className={cn(
        "flex h-[60px] shrink-0 items-center justify-center gap-2 rounded-2xl border px-5 text-[17px] font-semibold whitespace-nowrap",
        tone === "done"
          ? "border-mint bg-mint-pale text-mint-ink"
          : tone === "on"
            ? "border-navy bg-white text-navy"
            : "border-line-2 bg-white text-ash-2",
      )}
    >
      {busy && <Spinner tone="brand" className="size-4 border-blush border-t-navy" />}
      {children}
    </button>
  );
}

/** 한글 조합 중이 아닐 때 Enter로 동작을 실행한다 */
export const onEnter = (action: () => void) => (e: React.KeyboardEvent<HTMLInputElement>) => {
  if (e.key !== "Enter" || e.nativeEvent.isComposing) return;
  e.preventDefault();
  action();
};
