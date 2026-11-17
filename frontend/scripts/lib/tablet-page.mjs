// 개발 서버의 화면을 USB로 연결한 안드로이드 태블릿(Chrome)에서 열고, 원격 디버깅(CDP)으로 값을 읽는 공용 도구.
// occlusion-bench.mjs · occlusion-live.mjs가 쓴다. 종료 코드: 0 성공, 1 실패, 2 사람이 해 줘야 하는 일
import { execFileSync, spawn } from "node:child_process";
import { existsSync, mkdtempSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";

export const say = (text) => console.log(`[측정] ${text}`);
export const needHuman = (text) => {
  console.error(`[사람 도움 필요] ${text}`);
  process.exitCode = 2;
};
export const fail = (text) => {
  console.error(`[측정 실패] ${text}`);
  process.exitCode = process.exitCode || 1;
};
export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** `--이름 값` 옵션을 읽는다 */
export const option = (args, name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback;
};

function findAdb() {
  if (process.env.ADB) return process.env.ADB;
  const exe = process.platform === "win32" ? "adb.exe" : "adb";
  const candidates = [
    join(homedir(), "platform-tools", exe),
    join(process.env.LOCALAPPDATA ?? "", "Android", "Sdk", "platform-tools", exe),
    join(homedir(), "Library", "Android", "sdk", "platform-tools", exe),
    join(homedir(), "Android", "Sdk", "platform-tools", exe),
  ];
  try {
    execFileSync(exe, ["version"], { stdio: "ignore" });
    return exe;
  } catch {
    return candidates.find((path) => existsSync(path)) ?? null;
  }
}

/**
 * 화면을 열고 연결한다. 사람이 해 줘야 하는 일이 있거나 실패하면 이유를 출력하고 null을 낸다.
 * 성공하면 { evaluate(expression), close() }를 낸다. close는 연결 · 탭을 정리하므로 반드시 부른다
 * - pagePath: 열 화면 경로(예: /debug/occlusion-bench), query: 붙일 쿼리(예: auto=1)
 * - checkModel: 가림 모델 파일(LFS)이 제대로 서빙되는지 먼저 본다
 * - localChromeArgs: 시험용(--local-chrome)으로 PC Chrome을 띄울 때 더 붙일 인자
 */
export async function openTabletPage({
  args,
  pagePath,
  query = "",
  checkModel = false,
  localChromeArgs = [],
  tag = "tablet",
}) {
  const PORT = Number(option(args, "port", "3000"));
  const CDP_PORT = Number(option(args, "cdp-port", "9333"));
  const LOCAL = args.includes("--local-chrome");

  if (Number(process.versions.node.split(".")[0]) < 22) {
    fail(
      `Node 22 이상이 필요합니다(지금 ${process.versions.node}). Node를 올린 뒤 다시 실행하세요`,
    );
    return null;
  }

  // 기기
  const adb = LOCAL ? null : findAdb();
  if (!LOCAL && !adb) {
    needHuman(
      "adb를 찾지 못했습니다. Android Platform Tools를 설치하고 PATH에 넣거나 ADB 환경 변수에 adb 경로를 적어 주세요",
    );
    return null;
  }
  const run = (list, options = {}) =>
    execFileSync(adb, list, { encoding: "utf8", timeout: 30000, ...options }).toString();
  let device = null;
  if (!LOCAL) {
    const devices = run(["devices"])
      .split("\n")
      .slice(1)
      .map((l) => l.trim())
      .filter(Boolean)
      .map((l) => l.split(/\s+/))
      .map(([serial, state]) => ({ serial, state }));
    const ready = devices.filter((d) => d.state === "device");
    const wanted = option(args, "serial", null);
    if (devices.some((d) => d.state === "unauthorized") && ready.length === 0) {
      needHuman(
        "태블릿 화면에 'USB 디버깅을 허용하시겠습니까?' 창이 떠 있습니다. '허용'을 누른 뒤 다시 실행하세요",
      );
      return null;
    }
    if (ready.length === 0) {
      needHuman(
        `연결된 기기가 없습니다(adb devices: ${devices.map((d) => `${d.serial}:${d.state}`).join(", ") || "비어 있음"}). USB 케이블을 연결하고 개발자 옵션의 USB 디버깅을 켠 뒤 다시 실행하세요`,
      );
      return null;
    }
    device = wanted ? ready.find((d) => d.serial === wanted) : ready.length === 1 ? ready[0] : null;
    if (!device) {
      needHuman(
        `기기가 ${ready.length}대입니다. --serial <기기 번호>로 하나를 고르세요: ${ready.map((d) => d.serial).join(", ")}`,
      );
      return null;
    }
  }
  const dev = (list, options) => (LOCAL ? "" : run(["-s", device.serial, ...list], options));
  if (LOCAL) say("시험용: 이 PC의 Chrome으로 진행합니다(--local-chrome)");
  else
    say(
      `기기: ${device.serial} (${dev(["shell", "getprop", "ro.product.model"]).trim()}, Android ${dev(["shell", "getprop", "ro.build.version.release"]).trim()})`,
    );

  let tabId = null;
  let localChrome = null;
  let ws = null;
  const close = async () => {
    try {
      ws?.close();
    } catch {
      // 이미 닫혔으면 넘어간다
    }
    try {
      if (tabId) await fetch(`http://127.0.0.1:${CDP_PORT}/json/close/${tabId}`);
    } catch {
      // 탭이 이미 닫혔으면 넘어간다
    }
    localChrome?.kill();
    for (const list of [
      ["forward", "--remove", `tcp:${CDP_PORT}`],
      ["reverse", "--remove", `tcp:${PORT}`],
    ]) {
      try {
        dev(list, { stdio: "ignore" });
      } catch {
        // 설정이 없었으면 넘어간다
      }
    }
  };

  try {
    // 개발 서버 · 모델 파일
    try {
      const page = await fetch(`http://localhost:${PORT}${pagePath}`, {
        signal: AbortSignal.timeout(90000),
      });
      if (!page.ok) throw new Error(`HTTP ${page.status}`);
    } catch (e) {
      needHuman(
        `개발 서버(http://localhost:${PORT}${pagePath})에 연결하지 못했습니다(${e.message}). frontend 폴더에서 npm run dev를 켜 둔 상태로 다시 실행하세요`,
      );
      await close();
      return null;
    }
    if (checkModel) {
      const model = await fetch(
        `http://localhost:${PORT}/models/occlusion_bisenet.v1.web.fp16.onnx`,
        { method: "HEAD" },
      );
      const size = Number(model.headers.get("content-length"));
      if (!model.ok || size !== 26321817) {
        fail(
          `모델 파일이 맞지 않습니다(받은 크기 ${size || "없음"}, 기대 26321817). Git LFS를 받지 않았을 수 있습니다: 저장소 루트에서 git lfs pull 후 frontend에서 npm run dev를 다시 켜세요`,
        );
        await close();
        return null;
      }
    }
    if (
      !LOCAL &&
      !dev(["shell", "pm", "list", "packages", "com.android.chrome"]).includes("com.android.chrome")
    ) {
      fail("태블릿에 Chrome(com.android.chrome)이 없습니다");
      await close();
      return null;
    }

    // 화면 켜기 · 잠금 확인
    if (!LOCAL) dev(["shell", "input", "keyevent", "KEYCODE_WAKEUP"]);
    for (let waited = 0; !LOCAL; waited += 3) {
      if (!/isKeyguardShowing=true/.test(dev(["shell", "dumpsys", "window"]))) break;
      if (waited === 0)
        needHuman(
          "태블릿 화면이 잠겨 있습니다. 잠금을 풀어 주세요(기다리는 중, 최대 2분). 진행 중에는 화면이 꺼지지 않게 두세요",
        );
      if (waited >= 120) {
        fail("2분 안에 잠금이 풀리지 않았습니다");
        process.exitCode = 2;
        await close();
        return null;
      }
      await sleep(3000);
    }
    process.exitCode = 0;

    const url = `http://localhost:${PORT}${pagePath}?${query ? `${query}&` : ""}t=${Date.now()}`;
    if (LOCAL) {
      const chrome = [
        process.env.CHROME,
        "C:/Program Files/Google/Chrome/Application/chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "google-chrome",
      ].find((path) => path && (path === "google-chrome" || existsSync(path)));
      localChrome = spawn(
        chrome,
        [
          `--remote-debugging-port=${CDP_PORT}`,
          `--user-data-dir=${mkdtempSync(join(tmpdir(), `${tag}-`))}`,
          "--no-first-run",
          "--no-default-browser-check",
          "--headless=new",
          ...localChromeArgs,
          url,
        ],
        { stdio: "ignore" },
      );
      say("PC Chrome(화면 없이)에서 화면을 열었습니다");
    } else {
      dev(["reverse", `tcp:${PORT}`, `tcp:${PORT}`]);
      dev(["forward", `tcp:${CDP_PORT}`, "localabstract:chrome_devtools_remote"]);
      dev(["shell", `am start -a android.intent.action.VIEW -d '${url}' com.android.chrome`]);
      say("태블릿 Chrome에서 화면을 열었습니다. 끝날 때까지 화면을 켜 두세요");
    }

    // 열린 탭을 찾아 연결한다
    let tab = null;
    for (let i = 0; i < 30 && !tab; i++) {
      try {
        const list = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json();
        tab = list.find((t) => t.type === "page" && t.url.includes(pagePath));
      } catch {
        // Chrome이 아직 디버그 포트를 열지 않았다
      }
      if (!tab) await sleep(1000);
    }
    if (!tab) {
      fail("태블릿 Chrome 탭을 찾지 못했습니다(원격 디버깅 연결 실패)");
      await close();
      return null;
    }
    tabId = tab.id;
    ws = new WebSocket(tab.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      ws.onopen = resolve;
      ws.onerror = () => reject(new Error("원격 디버깅 연결 실패"));
    });
    let seq = 0;
    const evaluate = (expression) =>
      new Promise((resolve, reject) => {
        const id = ++seq;
        const timer = setTimeout(() => reject(new Error("응답 없음")), 15000);
        const onMessage = (event) => {
          const data = JSON.parse(event.data);
          if (data.id !== id) return;
          clearTimeout(timer);
          ws.removeEventListener("message", onMessage);
          resolve(data.result?.result?.value);
        };
        ws.addEventListener("message", onMessage);
        ws.send(
          JSON.stringify({
            id,
            method: "Runtime.evaluate",
            params: { expression, returnByValue: true },
          }),
        );
      });
    return { evaluate, close };
  } catch (e) {
    fail(e instanceof Error ? e.message : String(e));
    await close();
    return null;
  }
}
