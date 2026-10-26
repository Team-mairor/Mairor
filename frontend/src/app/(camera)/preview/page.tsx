"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { MakeupOverlay } from "@/features/overlay";

const DEFAULT_LAYERS = "/fixtures/layers/sample.json";

export default function PreviewPage() {
  // 레시피 연동 전까지는 ?layers=경로 로 레이어 파일을 바꿔 본다.
  const [layersUrl, setLayersUrl] = useState<string | null>(null);
  useEffect(() => {
    const param = new URLSearchParams(window.location.search).get("layers");
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 주소창 값은 브라우저에서만 읽을 수 있다
    setLayersUrl(param ?? DEFAULT_LAYERS);
  }, []);

  return (
    <main className="relative flex flex-1 flex-col items-center justify-end gap-6 p-8">
      <MakeupOverlay layersUrl={layersUrl} />
      <Button asChild size="lg" className="relative">
        <Link href="/tutorial">튜토리얼 시작</Link>
      </Button>
    </main>
  );
}
