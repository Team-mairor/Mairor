import { cn } from "@/lib/utils";

export function Spinner({
  className,
  tone = "light",
}: {
  className?: string;
  /** light: 흰 버튼 글자 위, brand: 흰 배경 위 */
  tone?: "light" | "brand";
}) {
  return (
    <span
      role="status"
      aria-label="처리 중"
      className={cn(
        "inline-block size-7 shrink-0 animate-spin rounded-full border-[2.5px]",
        tone === "light" ? "border-white/40 border-t-white" : "border-line border-t-ice",
        className,
      )}
    />
  );
}
