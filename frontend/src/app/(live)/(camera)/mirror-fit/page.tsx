"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { MirrorFitView } from "@/features/mirror-fit";
import { useQuery } from "@/lib/hooks/use-query";
import { isMirror, setMirror } from "@/lib/mirror";
import { useHiddenVideo } from "@/vision/face";

/** 거울 맞추기. ?first=1이면 미러필름을 처음 켜서 들어온 것이다. 저장하거나 취소하면 돌아간다 */
export default function MirrorFitPage() {
  const router = useRouter();
  const first = useQuery()?.get("first") === "1";

  // 이 화면에서만 미러필름 모드로 두고, 나가면 원래 모드로 돌린다
  useHiddenVideo();
  useEffect(() => {
    const before = isMirror();
    setMirror(true);
    return () => setMirror(before);
  }, []);

  return (
    <main className="relative flex flex-1 flex-col">
      {/* 주소로 바로 열어 돌아갈 곳이 없으면 홈으로 간다 */}
      <MirrorFitView
        first={first}
        onClose={() => (history.length > 1 ? router.back() : router.replace("/home"))}
      />
    </main>
  );
}
