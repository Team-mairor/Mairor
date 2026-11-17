// 실제 Chrome/Edge Canvas로 합성 결과를 검증한다. 최종 디자인 검수용 이미지는 아니다.
// PHOTO_BROWSER_PATH로 실행할 Chromium 계열 브라우저를 지정할 수 있다.
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { build } from "esbuild";

const frontend = fileURLToPath(new URL("../", import.meta.url));
const browser = [
  process.env.PHOTO_BROWSER_PATH,
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
].find((candidate) => candidate && existsSync(candidate));
if (!browser) throw new Error("PHOTO_BROWSER_PATH에 Chrome/Edge 실행 파일을 지정해 주세요.");

const directory = mkdtempSync(path.join(tmpdir(), "mairor-photo-frame-"));
const bundle = await build({
  absWorkingDir: frontend,
  // index.ts는 화면 컴포넌트(next/link 등)도 내보내므로 합성 함수만 묶는다
  stdin: {
    contents:
      'export { renderPhotoFrame } from "./render"; export { createPhotoJpegBlob, createPhotoJpegFilename } from "./export-jpeg";',
    resolveDir: "src/features/photo-booth",
    loader: "ts",
  },
  bundle: true,
  write: false,
  format: "iife",
  globalName: "PhotoBooth",
  platform: "browser",
});
const html = `<!doctype html><meta charset="utf-8"><canvas id="output"></canvas><pre id="result"></pre>
<script>${bundle.outputFiles[0].text.replaceAll("</script", "<\\/script")}</script>
<script>
void (async () => {
try {
  const frame = {
    id: 'check-grid', version: 1,
    output: { width: 1200, height: 1800, background: '#ffffff' },
    slots: [
      { id: 'slot-1', x: 60, y: 60, width: 520, height: 760 },
      { id: 'slot-2', x: 620, y: 60, width: 520, height: 760 },
      { id: 'slot-3', x: 60, y: 860, width: 520, height: 760 },
      { id: 'slot-4', x: 620, y: 860, width: 520, height: 760 },
    ],
  };
  const { renderPhotoFrame, createPhotoJpegBlob, createPhotoJpegFilename } = PhotoBooth;
  const makeImage = (left, right = left) => {
    const image = document.createElement('canvas');
    image.width = image.height = 200;
    const ctx = image.getContext('2d');
    ctx.fillStyle = left; ctx.fillRect(0, 0, 100, 200);
    ctx.fillStyle = right; ctx.fillRect(100, 0, 100, 200);
    return image;
  };
  const canvas = document.getElementById('output');
  const split = makeImage('#ff0000', '#0000ff');
  const photos = {
    'slot-1': { image: split, placement: { mirrored: true } },
    'slot-2': { image: split },
    'slot-3': { image: makeImage('#00ff00') },
    'slot-4': { image: makeImage('#ffff00') },
  };
  renderPhotoFrame(canvas, frame, photos);
  const ctx = canvas.getContext('2d');
  const pixel = (x, y) => [...ctx.getImageData(x, y, 1, 1).data].join(',');
  const checks = [
    [10, 10, '255,255,255,255'],
    [100, 300, '0,0,255,255'],
    [530, 300, '255,0,0,255'],
    [660, 300, '255,0,0,255'],
    [1090, 300, '0,0,255,255'],
    [300, 1100, '0,255,0,255'],
    [850, 1100, '255,255,0,255'],
  ];
  for (const [x, y, expected] of checks) {
    if (pixel(x, y) !== expected) throw new Error('pixel mismatch: ' + [x, y, pixel(x, y)]);
  }
  const overlay = document.createElement('canvas');
  overlay.width = frame.output.width; overlay.height = frame.output.height;
  const overlayCtx = overlay.getContext('2d');
  overlayCtx.fillStyle = '#00ffff'; overlayCtx.fillRect(80, 80, 100, 100);
  renderPhotoFrame(canvas, { ...frame, overlaySrc: '/frames/check.png' }, photos, overlay);
  if (pixel(100, 100) !== '0,255,255,255') throw new Error('overlay must be above photos');

  const jpeg = await createPhotoJpegBlob(canvas);
  if (jpeg.type !== 'image/jpeg' || jpeg.size <= 0) throw new Error('invalid JPEG Blob');
  const decoded = await createImageBitmap(jpeg);
  if (decoded.width !== frame.output.width || decoded.height !== frame.output.height) {
    throw new Error('JPEG dimensions do not match the frame output');
  }
  const jpegWidth = decoded.width;
  const jpegHeight = decoded.height;
  decoded.close();
  const filename = createPhotoJpegFilename(new Date(2026, 0, 2, 3, 4, 5));
  if (filename !== 'mairor-4cut-20260102-030405.jpg') throw new Error('unexpected JPEG filename: ' + filename);
  const jpegDataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => typeof reader.result === 'string' ? resolve(reader.result) : reject(new Error('failed to read JPEG'));
    reader.onerror = () => reject(reader.error ?? new Error('failed to read JPEG'));
    reader.readAsDataURL(jpeg);
  });
  document.getElementById('result').textContent = JSON.stringify({
    passed: true,
    checks: checks.length + 1,
    width: jpegWidth,
    height: jpegHeight,
    filename,
    jpegDataUrl,
    png: canvas.toDataURL('image/png'),
  });
} catch (error) {
  document.getElementById('result').textContent = JSON.stringify({ passed: false, message: String(error) });
}
})();
</script>`;
const input = path.join(directory, "check.html");
writeFileSync(input, html);
const dom = execFileSync(
  browser,
  [
    "--headless=new",
    "--disable-gpu",
    "--no-first-run",
    "--virtual-time-budget=5000",
    `--user-data-dir=${path.join(directory, "browser-profile")}`,
    "--dump-dom",
    pathToFileURL(input).href,
  ],
  {
    encoding: "utf8",
    timeout: 30000,
    maxBuffer: 10 * 1024 * 1024,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  },
);
const match = dom.match(/<pre id="result">([^<]+)<\/pre>/);
if (!match) throw new Error(`브라우저 검증 결과가 없습니다: ${directory}`);
const result = JSON.parse(match[1]);
if (!result.passed) throw new Error(result.message);
const output = path.join(directory, "composite.png");
writeFileSync(output, Buffer.from(result.png.split(",")[1], "base64"));
if (!readFileSync(output).length) throw new Error("합성 이미지가 비어 있습니다.");
if (
  result.width !== 1200 ||
  result.height !== 1800 ||
  result.filename !== "mairor-4cut-20260102-030405.jpg" ||
  !result.jpegDataUrl.startsWith("data:image/jpeg;base64,")
) {
  throw new Error(`JPEG output contract mismatch: ${JSON.stringify(result)}`);
}
const jpegOutput = path.join(directory, result.filename);
const jpegBytes = Buffer.from(result.jpegDataUrl.split(",")[1], "base64");
if (!jpegBytes.length || jpegBytes.readUInt16BE(0) !== 0xffd8) {
  throw new Error("JPEG file is empty or missing the SOI marker.");
}
writeFileSync(jpegOutput, jpegBytes);
console.log(
  `PASS: ${result.checks} browser pixel checks; JPEG ${result.width}×${result.height}, ${jpegBytes.length} bytes. Image: ${jpegOutput}`,
);
