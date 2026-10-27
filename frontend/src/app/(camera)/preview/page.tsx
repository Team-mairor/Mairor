"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { applyLandmarkerParams } from "@/features/face";
import { MakeupOverlay } from "@/features/overlay";

const DEFAULT_LAYERS = "/fixtures/layers/sample.json";

export default function PreviewPage() {
  // 레시피 연동 전까지는 주소로 확인 조건을 바꾼다.
  //   ?layers=경로  레이어 파일
  //   ?overlay=off  레이어를 그리지 않음 (추적만 할 때와 성능 비교)
  //   ?stats        FPS·처리 시간 표시
  //   ?occlusion=off 앞머리·손 등 가림을 반영하지 않음
  //   ?delegate=gpu|cpu, ?blendshapes=off  얼굴 추적 실행 방식 (기기별 성능 비교)
  // 주소를 읽기 전(null)에는 오버레이를 만들지 않는다. 기본값으로 분할 모델을 불렀다가 버리면 비교가 어긋난다.
  const [options, setOptions] = useState<{
    layersUrl: string;
    overlay: boolean;
    stats: boolean;
    occlusion: boolean;
  } | null>(null);
  useEffect(() => {
    // 카메라를 여는 CameraProvider의 effect보다 먼저 돌아, 추적 모델을 만들기 전에 적용된다.
    applyLandmarkerParams(window.location.search);
    const params = new URLSearchParams(window.location.search);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- 주소창 값은 브라우저에서만 읽을 수 있다
    setOptions({
      layersUrl: params.get("layers") ?? DEFAULT_LAYERS,
      overlay: params.get("overlay") !== "off",
      stats: params.has("stats"),
      occlusion: params.get("occlusion") !== "off",
    });
  }, []);

  return (
    <main className="relative flex flex-1 flex-col items-center justify-end gap-6 p-8">
      {options && (
        <MakeupOverlay
          layersUrl={options.layersUrl}
          enabled={options.overlay}
          showStats={options.stats}
          occlusion={options.occlusion}
        />
      )}
      <Button asChild size="lg" className="relative">
        <Link href="/tutorial">튜토리얼 시작</Link>
      </Button>
    </main>
  );
}
