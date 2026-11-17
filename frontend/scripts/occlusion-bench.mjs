// 가림 찾기 모델 속도를 USB로 연결한 안드로이드 태블릿(Chrome)에서 자동으로 잰다.
// 사용: 개발 서버(npm run dev)를 켠 뒤 `npm run occlusion:bench` (Node 22 이상, adb 필요)
//   옵션: --port 3000 --serial <기기 번호> --timeout 420 --cdp-port 9333 --out occlusion-bench-result.json
//   시험용: --local-chrome (기기 없이 이 PC의 Chrome으로 같은 흐름을 확인)
// 끝나면 occlusion-bench-result.json을 쓰고 요약을 출력한다. 정리(adb reverse · forward, 탭 닫기)까지 한다.
// 종료 코드: 0 성공, 1 측정 실패, 2 사람이 해 줘야 하는 일(케이블 · USB 디버깅 허용 · 잠금 해제 · 개발 서버)
import { writeFileSync } from "node:fs";

import { fail, openTabletPage, option, say, sleep } from "./lib/tablet-page.mjs";

const args = process.argv.slice(2);
const TIMEOUT_S = Number(option(args, "timeout", "420"));
const OUT = option(args, "out", "occlusion-bench-result.json");

const session = await openTabletPage({
  args,
  pagePath: "/debug/occlusion-bench",
  query: "auto=1",
  checkModel: true,
  tag: "occ-bench",
});

if (session) {
  try {
    const started = Date.now();
    let lastState = "";
    let result = null;
    while (Date.now() - started < TIMEOUT_S * 1000) {
      const value = await session
        .evaluate(
          "JSON.stringify({ state: window.__OCC_BENCH_STATE__ || '', done: !!(window.__OCC_BENCH__ && window.__OCC_BENCH__.done) })",
        )
        .catch(() => null);
      if (value) {
        const { state, done } = JSON.parse(value);
        if (state && state !== lastState) {
          say(state);
          lastState = state;
        }
        if (done) {
          result = JSON.parse(await session.evaluate("JSON.stringify(window.__OCC_BENCH__)"));
          break;
        }
      }
      await sleep(2000);
    }
    if (!result) {
      fail(
        `${TIMEOUT_S}초 안에 측정이 끝나지 않았습니다(마지막 상태: ${lastState || "없음"}). 태블릿 화면이 꺼졌거나 Chrome이 백그라운드로 갔는지 확인하세요`,
      );
    } else {
      writeFileSync(OUT, JSON.stringify(result, null, 2));
      say(`결과 파일: ${OUT}`);
      console.log("\n방식    입력  열기ms  가운데ms  90%ms   결과");
      for (const r of result.runs) {
        const cell = (v) => String(v ?? "-").padStart(7);
        console.log(
          `${r.provider.padEnd(7)} ${String(r.size).padEnd(5)} ${cell(r.loadMs)} ${cell(r.runMs?.median)} ${cell(r.runMs?.p90)}   ${r.ok ? "정상" : `실패: ${r.error}`}`,
        );
      }
      const gpu = result.env.gpu;
      console.log(
        `\nWebGPU: api=${gpu?.api} adapter=${gpu?.adapter} f16=${gpu?.shaderF16 ?? "?"} ${gpu?.vendor ?? ""} ${gpu?.architecture ?? ""}`,
      );
      console.log(`기기: ${result.env.userAgent}`);
      if (result.error) fail(`화면 안 오류: ${result.error}`);
    }
  } catch (e) {
    fail(e instanceof Error ? e.message : String(e));
  } finally {
    await session.close();
  }
}
