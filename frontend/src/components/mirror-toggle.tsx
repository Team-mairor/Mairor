"use client";

import { useRouter } from "next/navigation";
import { useSyncExternalStore } from "react";

import { isMirror, MIRROR_KEY, setMirror, subscribeMirror } from "@/lib/mirror";
import { cn } from "@/lib/utils";
import { hasMirrorFit } from "@/vision/face";

/**
 * 일반 / 미러필름 모드 전환. 색 규칙은 globals.css의 .mirror.
 * fitFirst면 거울 맞추기를 한 적 없이 켤 때 거울 맞추기 화면으로 보낸다. 확인 화면에서는 그 자리에서 바꾸기만 한다
 */
export function MirrorToggle({
  className,
  fitFirst = false,
}: {
  className?: string;
  fitFirst?: boolean;
}) {
  const router = useRouter();
  // <html>의 mirror 클래스를 구독해, 화면에 토글이 여러 개 있어도 같은 상태를 보여 준다
  const on = useSyncExternalStore(subscribeMirror, isMirror, () => false);

  const toggle = () => {
    const next = !on;
    setMirror(next);
    try {
      localStorage.setItem(MIRROR_KEY, next ? "1" : "0");
    } catch {
      // 저장에 실패해도 지금 화면에는 적용된다
    }
    if (fitFirst && next && !hasMirrorFit()) router.push("/mirror-fit?first=1");
  };

  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={toggle}
      className={cn(
        "flex h-11 shrink-0 items-center gap-2.5 rounded-full border border-line-2 bg-white pr-2 pl-4 text-[16px] font-semibold whitespace-nowrap text-ink",
        className,
      )}
    >
      미러필름
      <span
        className={cn(
          "relative h-6 w-10 rounded-full transition-colors",
          on ? "bg-cyan" : "bg-line-2",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 left-0.5 size-5 rounded-full bg-white transition-transform",
            on && "translate-x-4",
          )}
        />
      </span>
    </button>
  );
}
