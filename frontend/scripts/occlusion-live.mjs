// 가림 찾기를 USB로 연결한 안드로이드 태블릿(Chrome)에서 실제 카메라로 확인한다.
// 사용: 개발 서버(npm run dev)를 켠 뒤 `npm run occlusion:live` (Node 22 이상, adb 필요)
//   옵션: --port 3000 --serial <기기 번호> --cdp-port 9333 --out occlusion-live-result.json
//   시험용: --local-chrome (기기 없이 PC Chrome + 가짜 카메라로 흐름만 확인), --skip-face-check (얼굴이 없어도 진행)
// 태블릿 화면에 큰 글자 · 카운트다운 · 진동으로 손동작을 안내하고, 단계마다 가린 몫 · 얼굴 추적 FPS · 가림 찾기 상태를 모아
// occlusion-live-result.json과 보고용 요약을 낸다. 사람은 화면 글자대로 하면 되고 값을 볼 필요가 없다.
// 종료 코드: 0 성공, 1 실패, 2 사람이 해 줘야 하는 일(케이블 · USB 디버깅 허용 · 잠금 해제 · 카메라 허용 · 얼굴 맞추기)
import { writeFileSync } from "node:fs";

import { fail, needHuman, openTabletPage, option, say, sleep } from "./lib/tablet-page.mjs";

const args = process.argv.slice(2);
const OUT = option(args, "out", "occlusion-live-result.json");
const SKIP_FACE = args.includes("--skip-face-check");
// 시험할 때 단계 시간을 줄이는 배율(기본 1)
const SCALE = Number(option(args, "scale", "1"));

const PHASES = [
  { phase: "face", seconds: 15, occlusion: true, text: "얼굴을 화면 가운데에 두고 가만히 계세요" },
  {
    phase: "hand",
    seconds: 15,
    occlusion: true,
    text: "손바닥으로 한쪽 볼을 가리고 그대로 계세요(눈 · 코는 보이게)",
  },
  {
    phase: "mouth",
    seconds: 12,
    occlusion: true,
    text: "손바닥이나 손가락으로 입 쪽을 가리고 그대로 계세요(눈은 보이게)",
  },
  { phase: "clear", seconds: 10, occlusion: true, text: "손을 내리고 가만히 계세요" },
  {
    phase: "move",
    seconds: 12,
    occlusion: true,
    text: "손바닥을 얼굴 앞에서 천천히 좌우로 움직여 주세요",
  },
  {
    phase: "off",
    seconds: 15,
    occlusion: false,
    text: "(가림 찾기를 끈 상태) 손을 내리고 가만히 계세요",
  },
];
const END = { phase: "done", seconds: 0, occlusion: true, text: "끝났습니다. 고맙습니다" };

const session = await openTabletPage({
  args,
  pagePath: "/debug/occlusion-live",
  query: "",
  checkModel: true,
  localChromeArgs: [
    "--use-fake-device-for-media-stream",
    "--use-fake-ui-for-media-stream",
    "--autoplay-policy=no-user-gesture-required",
  ],
  tag: "occ-live",
});

const read = async (expression) => {
  const value = await session.evaluate(expression);
  return value ? JSON.parse(value) : null;
};
const live = () => read("JSON.stringify(window.__OCC_LIVE__ || null)");

const pct = (a, b) => (b ? Math.round((a / b) * 100) : null);

function summarize(phases, occlusion) {
  const by = Object.fromEntries(phases.map((p) => [p.phase, p]));
  const avg = (values) => {
    const v = values.filter((x) => x !== null && x !== undefined);
    return v.length ? Math.round((v.reduce((a, b) => a + b, 0) / v.length) * 10) / 10 : null;
  };
  const fpsOn = avg([by.face?.fps, by.clear?.fps]);
  const fpsOff = by.off?.fps ?? null;
  const overRatio = (p) => (p ? pct(p.overFrames, p.zoneSamples) : null);
  const lines = [];
  lines.push(
    `가림 찾기 상태: ${occlusion?.state ?? "-"}${occlusion?.provider ? ` (${occlusion.provider})` : ""}, 처리 ${occlusion?.runMs ?? "-"}ms, 실행 간격 ${occlusion?.intervalMs ?? "-"}ms${occlusion?.reason ? `, 이유: ${occlusion.reason}` : ""}`,
  );
  lines.push(
    `얼굴 추적 FPS: 가림 찾기 켬 ${fpsOn ?? "-"} / 끔 ${fpsOff ?? "-"}${fpsOn && fpsOff ? ` (차이 ${Math.round(((fpsOff - fpsOn) / fpsOff) * 100)}%)` : ""}`,
  );
  const hand = by.hand;
  lines.push(
    `손으로 가림: 가린 몫(가장 많이 가린 구역) 평균 ${hand?.maxZoneMean ?? "-"} · 최대 ${hand?.maxZoneMax ?? "-"}, 문턱 0.2 넘은 비율 ${overRatio(hand) ?? "-"}%, 처음 넘은 시각 ${hand?.firstOverMs ?? "-"}ms(손 올리는 시간 포함, 참고) (얼굴 보인 결과 ${hand?.faceFrames ?? 0}/${hand?.frames ?? 0})`,
  );
  lines.push(
    `손 없을 때 오탐: 얼굴만 ${overRatio(by.face) ?? "-"}% · 손 내린 뒤 ${overRatio(by.clear) ?? "-"}% (문턱 0.2 넘은 비율, 단계가 바뀐 뒤 4초는 뺌)`,
  );
  lines.push(
    `손을 움직일 때: 문턱 넘은 비율 ${overRatio(by.move) ?? "-"}%, 가린 몫 최대 ${by.move?.maxZoneMax ?? "-"}`,
  );
  const mouth = by.mouth;
  lines.push(
    `입 가림: 가린 몫 평균 ${mouth?.maxZoneMean ?? "-"} · 최대 ${mouth?.maxZoneMax ?? "-"}, 문턱 넘은 비율 ${overRatio(mouth) ?? "-"}%, 처음 넘은 시각 ${mouth?.firstOverMs ?? "-"}ms(손 올리는 시간 포함, 참고) (얼굴 보인 결과 ${mouth?.faceFrames ?? 0}/${mouth?.frames ?? 0})`,
  );
  const handOk = (overRatio(hand) ?? 0) >= 50;
  const mouthOk = (overRatio(mouth) ?? 0) >= 50;
  const noFalse = by.face?.zoneSamples || by.clear?.zoneSamples;
  const falseOk = (overRatio(by.face) ?? 0) <= 10 && (overRatio(by.clear) ?? 0) <= 10;
  const fpsOk = fpsOn && fpsOff ? (fpsOff - fpsOn) / fpsOff <= 0.2 : null;
  lines.push(
    `판정(참고): 볼 가림 ${hand?.zoneSamples ? (handOk ? "잡힘" : "못 잡음") : "표본 없음(가림 때 얼굴이 안 잡혔을 수 있음)"} / 입 가림 ${mouth?.zoneSamples ? (mouthOk ? "잡힘" : "못 잡음") : "표본 없음(가림 때 얼굴이 안 잡혔을 수 있음)"} / 오탐 ${noFalse ? (falseOk ? "적음" : "많음") : "표본 없음"} / FPS 영향 ${fpsOk === null ? "알 수 없음" : fpsOk ? "20% 이내" : "20% 넘게 떨어짐"}`,
  );
  return lines;
}

if (session) {
  try {
    // 준비: 카메라와 얼굴이 잡힐 때까지
    say("카메라와 얼굴 추적을 기다립니다");
    const started = Date.now();
    let asked = false;
    let state = null;
    while (Date.now() - started < 120_000) {
      state = await live().catch(() => null);
      if (state?.cameraStatus === "error") {
        needHuman(
          "태블릿 카메라를 열지 못했습니다. 카메라 권한(사이트 설정)과 다른 앱이 카메라를 쓰고 있지 않은지 확인해 주세요",
        );
        break;
      }
      if (state?.ready || (SKIP_FACE && state?.cameraStatus === "ready")) break;
      if (!asked && Date.now() - started > 15_000) {
        asked = true;
        needHuman(
          state?.cameraStatus === "ready"
            ? "태블릿을 얼굴 정면으로 들고 얼굴이 화면에 잘 보이게 해 주세요(진행 중이니 기다립니다)"
            : "태블릿에 카메라 권한 창이 떠 있으면 '허용'을 눌러 주세요(진행 중이니 기다립니다)",
        );
      }
      await sleep(1000);
    }
    process.exitCode = process.exitCode === 2 && !state?.ready ? 2 : 0;
    if (!state?.ready && !(SKIP_FACE && state?.cameraStatus === "ready")) {
      if (process.exitCode !== 2) fail("2분 안에 카메라와 얼굴 추적이 준비되지 않았습니다");
    } else {
      // 단계 진행
      for (const p of PHASES) {
        const seconds = Math.max(1, Math.round(p.seconds * SCALE));
        say(`${p.phase}: ${p.text} (${seconds}초)`);
        await session.evaluate(`window.__OCC_LIVE_CMD__(${JSON.stringify({ ...p, seconds })})`);
        await sleep(seconds * 1000);
      }
      await session.evaluate(`window.__OCC_LIVE_CMD__(${JSON.stringify(END)})`);
      const final = await live();
      const userAgent = await session.evaluate("navigator.userAgent");
      const phases = (final?.phases ?? []).filter((p) => p.phase !== "done");
      const summary = summarize(phases, final?.occlusion);
      const result = {
        version: 1,
        finishedAt: new Date().toISOString(),
        userAgent,
        summary,
        ...final,
      };
      writeFileSync(OUT, JSON.stringify(result, null, 2));
      say(`결과 파일: ${OUT}`);

      console.log("\n단계   켬  결과수 얼굴 FPS   가린몫평균 최대  넘은비율  처음넘음ms");
      for (const p of phases) {
        const cell = (v, w) => String(v ?? "-").padStart(w);
        console.log(
          `${p.phase.padEnd(6)} ${p.occlusionOn ? "O" : "X"} ${cell(p.frames, 6)} ${cell(p.faceFrames, 4)} ${cell(p.fps, 5)} ${cell(p.maxZoneMean, 9)} ${cell(p.maxZoneMax, 5)} ${cell(pct(p.overFrames, p.zoneSamples), 7)}% ${cell(p.firstOverMs, 9)}`,
        );
      }
      console.log("\n=== 보고용 요약 (사용자에게 그대로 전달) ===");
      for (const line of summary) console.log(`- ${line}`);
      console.log(`- 기기: ${userAgent}`);
      console.log("=== 끝 ===");
    }
  } catch (e) {
    fail(e instanceof Error ? e.message : String(e));
  } finally {
    await session.close();
  }
}
