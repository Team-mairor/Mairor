"use client";

import { useEffect, useState } from "react";

type Row = [string, string];

/** 지금 창에서 앱 화면이 쓰는 값. 시연 기기에서 열어 globals.css 기준 크기를 정할 때 쓴다 */
function measure(): Row[] {
  const vv = window.visualViewport;
  const px = (n: number | undefined) => (n === undefined ? "–" : `${Math.round(n * 10) / 10}px`);
  // 100dvh·100svh·100lvh는 CSS로만 알 수 있어 잠깐 요소를 붙여 잰다
  const probe = (unit: string) => {
    const el = document.createElement("div");
    el.style.cssText = `position:fixed;top:0;height:100${unit};visibility:hidden`;
    document.body.append(el);
    const h = el.getBoundingClientRect().height;
    el.remove();
    return h;
  };
  const mode = ["fullscreen", "standalone", "minimal-ui", "browser"].find(
    (m) => matchMedia(`(display-mode: ${m})`).matches,
  );
  return [
    ["innerWidth × innerHeight", `${px(innerWidth)} × ${px(innerHeight)}`],
    ["visualViewport", `${px(vv?.width)} × ${px(vv?.height)}`],
    ["100dvh / 100svh / 100lvh", `${px(probe("dvh"))} / ${px(probe("svh"))} / ${px(probe("lvh"))}`],
    ["screen.width × height", `${px(screen.width)} × ${px(screen.height)}`],
    ["screen.availHeight", px(screen.availHeight)],
    ["devicePixelRatio", String(devicePixelRatio)],
    // CSS 화면 크기에 DPR을 곱한 값이라 패널 해상도와 다를 수 있다 (S6 DPR 2.25에서 1602×2561)
    [
      "DPR 환산 해상도 (screen × DPR)",
      `${Math.round(screen.width * devicePixelRatio)} × ${Math.round(screen.height * devicePixelRatio)}`,
    ],
    ["방향", screen.orientation?.type ?? "–"],
    ["display-mode", mode ?? "–"],
    ["전체 화면", document.fullscreenElement ? "켜짐" : "꺼짐"],
    // globals.css의 --zoom과 같은 식. 이 화면은 확인 화면이라 실제로는 축소하지 않는다
    ["앱 축소 배율 (800×1200 기준)", Math.min(1, innerWidth / 800, probe("dvh") / 1200).toFixed(3)],
    ["userAgent", navigator.userAgent],
  ];
}

/** 화면 크기 확인. 창 크기·방향·주소창이 바뀌면 다시 잰다 */
export default function ScreenDebugPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [fullscreenError, setFullscreenError] = useState("");

  useEffect(() => {
    const update = () => setRows(measure());
    update();
    addEventListener("resize", update);
    window.visualViewport?.addEventListener("resize", update);
    document.addEventListener("fullscreenchange", update);
    return () => {
      removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("resize", update);
      document.removeEventListener("fullscreenchange", update);
    };
  }, []);

  // 기기·브라우저가 전체 화면을 막으면 아무 반응 없이 지나가지 않게 이유를 띄운다
  const toggleFullscreen = () => {
    setFullscreenError("");
    const el = document.documentElement;
    if (!document.fullscreenElement && !el.requestFullscreen) {
      setFullscreenError("이 브라우저는 전체 화면을 지원하지 않습니다");
      return;
    }
    (document.fullscreenElement ? document.exitFullscreen() : el.requestFullscreen()).catch(
      (e: unknown) => setFullscreenError(`전체 화면 실패: ${e instanceof Error ? e.message : e}`),
    );
  };

  return (
    // 미러필름 모드는 바탕을 검정으로 바꾸는데 data-debug는 글자만 검정으로 되돌려 안 보인다. 그래서 바탕을 직접 깐다.
    // data-debug가 --background를 흰색으로 되돌려 bg-background는 미러에서도 흰색이다. bg-white는 미러에서 검정으로 뒤집힌다
    <main className="min-h-dvh bg-background p-6">
      <h1 className="mb-4 text-xl font-bold">화면 크기</h1>
      {/* 키오스크(PWA fullscreen)와 같은 상태에서 재려고 주소창·상태바·내비 바를 숨긴다 */}
      <button
        type="button"
        className="mb-4 rounded border px-4 py-3 text-base"
        onClick={toggleFullscreen}
      >
        전체 화면 켜기/끄기
      </button>
      {fullscreenError && (
        <p role="alert" className="mb-4 text-sm text-destructive">
          {fullscreenError}
        </p>
      )}
      <table className="w-full text-sm">
        <tbody>
          {rows.map(([k, v]) => (
            <tr key={k} className="border-b align-top">
              <th className="py-2 pr-4 text-left font-medium whitespace-nowrap">{k}</th>
              <td className="py-2 break-all tabular-nums">{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
