"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { isMirror, setMirror } from "@/lib/mirror";
import {
  halfMirror,
  loadMirrorFit,
  MIN_IN_FRAME_RATIO,
  mirrorScreen,
  toScreen,
  useFaceFrame,
  useHiddenVideo,
  viewingEye,
  type FaceFrame,
  type MirrorFit,
  type MirrorScreen,
} from "@/vision/face";

type Px = { x: number; y: number };
type Kind = "pupil" | "nose" | "lips" | "chin" | "jaw";

const TOTAL = 7;

/** 자리별 얼굴 점 번호. 둘이면 같은 쪽 점을 쓴다 */
const LANDMARK: Record<Kind, number | [number, number]> = {
  pupil: [468, 473],
  nose: 1,
  lips: 13,
  chin: 152,
  jaw: [172, 397],
};

/** 손이 얼굴을 가리기 전 프레임도 남긴다(ms) */
const BEFORE_MS = 700;

/** 이보다 오래된 얼굴로는 찍지 않는다(ms). 얼굴을 놓치면 마지막 얼굴이 그대로 남는다 */
const STALE_MS = 1000;

type Snapshot = Pick<
  FaceFrame,
  "imageSize" | "landmarks" | "pose" | "transform" | "timestamp" | "trackingState" | "eyes"
>;

/** 한 점을 찍은 순간의 기록. 다시 계산할 수 있게 얼굴 점을 통째로 남긴다 */
interface Mark {
  /** 찍은 사람. 여러 사람이 같은 기기로 잴 때 나눠 본다 */
  who?: string;
  kind?: Kind;
  /** 좌우가 있는 자리는 같은 종류의 다른 점보다 화면 왼쪽인지 */
  side?: "left" | "right";
  tap: Px;
  screen: MirrorScreen;
  fit: MirrorFit;
  /** 찍은 순간의 얼굴. 손에 가려 불안정 상태여도 남긴다 */
  frame: Snapshot;
  /** 찍기 BEFORE_MS 전 얼굴 */
  before: Snapshot | null;
}

/** 예전에 기록을 두던 localStorage 키. 처음 열 때 IndexedDB로 옮기고 지운다 */
const OLD_KEY = "mairor-mirror-trace";
const WHO_KEY = "mairor-mirror-trace-who";
/** 기록 한 번이 얼굴 점 두 벌이라 100KB를 넘어 localStorage(5MB)에는 스무 번 남짓만 들어간다 */
const DB_NAME = "mairor-mirror-trace";
const STORE = "records";

const request = <T,>(req: IDBRequest<T>) =>
  new Promise<T>((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });

let dbReady: Promise<IDBDatabase> | null = null;

/** 기록 저장소를 연다. 예전 localStorage 기록이 있으면 한 번만 옮긴다 */
function openDb() {
  if (dbReady) return dbReady;
  const ready = (async () => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { autoIncrement: true });
    const db = await request(req);
    const old = localStorage.getItem(OLD_KEY);
    if (old) {
      const tx = db.transaction(STORE, "readwrite");
      for (const rec of JSON.parse(old) as Mark[][]) tx.objectStore(STORE).add(rec);
      await new Promise<void>((resolve, reject) => {
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
      });
      localStorage.removeItem(OLD_KEY);
    }
    return db;
  })();
  // 열기에 실패하면 남겨 두지 않아 다음 저장 때 다시 연다
  ready.catch(() => {
    if (dbReady === ready) dbReady = null;
  });
  dbReady = ready;
  return ready;
}

const readAll = async () =>
  request((await openDb()).transaction(STORE).objectStore(STORE).getAll()) as Promise<Mark[][]>;

const addRecord = async (rec: Mark[]) =>
  request((await openDb()).transaction(STORE, "readwrite").objectStore(STORE).add(rec));

/** 사람별 기록 수, 평균 오차, 평균 치우침(가로·세로 mm). 지금 계산 방식으로 다시 잰다 */
function summarize(all: Mark[][]) {
  const by = new Map<string, { n: number; dist: number[]; dx: number[]; dy: number[] }>();
  for (const rec of all) {
    const who = rec[0]?.who ?? "(이름 없음)";
    const row = by.get(who) ?? { n: 0, dist: [], dx: [], dy: [] };
    row.n += 1;
    for (const m of rec) {
      const p = predict(m);
      if (!p) continue;
      const dx = (p.x - m.tap.x) / m.screen.pxPerMm;
      const dy = (p.y - m.tap.y) / m.screen.pxPerMm;
      row.dist.push(Math.hypot(dx, dy));
      row.dx.push(dx);
      row.dy.push(dy);
    }
    by.set(who, row);
  }
  const mean = (v: number[]) => (v.length ? v.reduce((a, b) => a + b, 0) / v.length : 0);
  return [...by].map(([who, r]) => ({
    who,
    n: r.n,
    dist: mean(r.dist),
    dx: mean(r.dx),
    dy: mean(r.dy),
  }));
}

const snapshot = (f: FaceFrame): Snapshot => ({
  imageSize: f.imageSize,
  landmarks: f.landmarks,
  pose: f.pose,
  transform: f.transform,
  timestamp: f.timestamp,
  trackingState: f.trackingState,
  eyes: f.eyes,
});

/**
 * 턱까지 카메라에 들어오지 않을 만큼 가까운지. 앱도 이때는 화장을 숨긴다(trackingIssue).
 * 카메라 밖 자리는 추정이라 정답과 비교하면 계산 오차가 아니라 추정 오차를 재게 된다
 */
const isClose = (f: FaceFrame) => f.regionVisibility.faceOval.inFrameRatio < MIN_IN_FRAME_RATIO;

/** 찍은 순서와 상관없이 위치로 종류·좌우를 정한다 */
function classify(marks: Mark[]): Mark[] {
  if (marks.length < TOTAL) return marks;
  const byY = [...marks].sort((a, b) => a.tap.y - b.tap.y);
  const pupils = byY.slice(0, 2).sort((a, b) => a.tap.x - b.tap.x);
  const rest = byY.slice(2).sort((a, b) => a.tap.x - b.tap.x);
  const jaws = [rest[0], rest[rest.length - 1]];
  const middle = rest.slice(1, -1).sort((a, b) => a.tap.y - b.tap.y);
  const kinds = new Map<Mark, Pick<Mark, "kind" | "side">>([
    [pupils[0], { kind: "pupil", side: "left" }],
    [pupils[1], { kind: "pupil", side: "right" }],
    [jaws[0], { kind: "jaw", side: "left" }],
    [jaws[1], { kind: "jaw", side: "right" }],
    [middle[0], { kind: "nose" }],
    [middle[1], { kind: "lips" }],
    [middle[2], { kind: "chin" }],
  ]);
  return marks.map((m) => ({ ...m, ...kinds.get(m) }));
}

/** 지금 계산 방식으로 그 점이 그려지는 자리 */
function predict(mark: Mark): Px | null {
  if (!mark.kind) return null;
  const frame = mark.frame;
  // 찍은 순간의 얼굴만으로 판단하도록 시간으로 거르지 않은 보는 눈을 쓴다
  const r = halfMirror(
    frame,
    mark.screen,
    mark.fit,
    undefined,
    undefined,
    viewingEye(frame, mark.fit),
  );
  const at = (i: number) => toScreen(r.frame.landmarks[i], frame.imageSize, r.view);
  const index = LANDMARK[mark.kind];
  if (typeof index === "number") return at(index);
  const [a, b] = index.map(at);
  const leftFirst = a.x <= b.x;
  return mark.side === "left" ? (leftFirst ? a : b) : leftFirst ? b : a;
}

/** 하프미러 정답 찍기(개발용). 거울에 비친 자리를 S펜으로 찍어 계산과의 차이(mm)를 본다 */
export default function MirrorTracePage() {
  const areaRef = useRef<HTMLDivElement>(null);
  // 최근 얼굴들. 손에 가려 불안정해도 남긴다
  const recent = useRef<FaceFrame[]>([]);
  const [marks, setMarks] = useState<Mark[]>([]);
  const [savedCount, setSavedCount] = useState(0);
  /** 지금 찍은 점을 저장했는지. 같은 점이 두 번 저장되지 않게 한다 */
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  /** 방금 점을 버린 이유. 얼굴을 놓쳤거나(lost) 턱이 카메라 밖이었다(close) */
  const [missed, setMissed] = useState<"lost" | "close" | null>(null);
  /** 지금 턱까지 카메라에 들어오지 않을 만큼 가까운지 */
  const [close, setClose] = useState(false);
  const [who, setWho] = useState("");
  const [all, setAll] = useState<Mark[][]>([]);

  useHiddenVideo();
  useEffect(() => {
    const before = isMirror();
    setMirror(true);
    // 저장 횟수는 브라우저 저장소에서만 읽을 수 있다
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setWho(localStorage.getItem(WHO_KEY) ?? "");
    readAll()
      .then((saved) => {
        setAll(saved);
        setSavedCount(saved.length);
      })
      .catch((e: unknown) => setSaveError(e instanceof Error ? e.name : String(e)));
    return () => setMirror(before);
  }, []);

  useFaceFrame((frame) => {
    // 놓친 직후(hold)는 예전 얼굴 점이라 남기지 않는다
    if (!frame || frame.trackingState === "lost" || frame.trackingState === "hold") return;
    if (frame.landmarks.length < 478) return;
    setClose(isClose(frame));
    const list = recent.current;
    if (list[list.length - 1]?.timestamp === frame.timestamp) return;
    list.push(frame);
    while (list.length && frame.timestamp - list[0].timestamp > BEFORE_MS * 2) list.shift();
  });

  const tap = (e: React.PointerEvent<HTMLDivElement>) => {
    const area = areaRef.current;
    const list = recent.current;
    const frame = list[list.length - 1];
    if (!area || marks.length >= TOTAL) return;
    if (!frame || performance.now() - frame.timestamp > STALE_MS) {
      setMissed("lost");
      return;
    }
    if (isClose(frame)) {
      setMissed("close");
      return;
    }
    setMissed(null);
    const rect = area.getBoundingClientRect();
    const zoom = rect.width / area.clientWidth || 1;
    const p = { x: (e.clientX - rect.left) / zoom, y: (e.clientY - rect.top) / zoom };
    const before = [...list].reverse().find((f) => frame.timestamp - f.timestamp >= BEFORE_MS);
    setMarks((m) => [
      ...m,
      {
        who: who.trim() || undefined,
        tap: p,
        screen: mirrorScreen(area),
        fit: loadMirrorFit(),
        frame: snapshot(frame),
        before: before ? snapshot(before) : null,
      },
    ]);
  };

  const done = marks.length >= TOTAL;
  const shown = classify(marks);

  const save = async () => {
    setSaving(true);
    try {
      await addRecord(shown);
      const all = await readAll();
      setSavedCount(all.length);
      setAll(all);
      setSaveError(null);
      setSaved(true);
    } catch (e) {
      setSaveError(e instanceof Error ? e.name : String(e));
    } finally {
      setSaving(false);
    }
  };

  const exportAll = async () => {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(await readAll())], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `mirror-trace-${new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };
  const summary = summarize(all);

  return (
    <main className="relative flex min-h-0 flex-1 flex-col bg-night text-white">
      <div ref={areaRef} className="absolute inset-0 touch-none" onPointerDown={tap}>
        {shown.map((m, i) => {
          const p = done ? predict(m) : null;
          const mm = m.screen.pxPerMm;
          return (
            <div key={i}>
              <span
                className="absolute size-3 -translate-1/2 rounded-full bg-mint"
                style={{ left: m.tap.x, top: m.tap.y }}
              />
              {p && (
                <>
                  <span
                    className="absolute size-3 -translate-1/2 rounded-full bg-red-500"
                    style={{ left: p.x, top: p.y }}
                  />
                  <span
                    className="absolute text-xs whitespace-nowrap text-white/80"
                    style={{ left: m.tap.x + 8, top: m.tap.y + 6 }}
                  >
                    {((p.x - m.tap.x) / mm).toFixed(1)}, {((p.y - m.tap.y) / mm).toFixed(1)}mm
                  </span>
                </>
              )}
            </div>
          );
        })}
      </div>

      {/* 여러 명이 잴 때 찍기 전에 이름을 적는다. 비우면 「이름 없음」으로 묶는다 */}
      {/* 얼굴 위를 가리지 않게 칸은 내용만큼만 차지하고, 요약은 접어 둔다 */}
      <div className="relative mx-6 mt-4 flex flex-col gap-2 self-start rounded-xl bg-night/80 p-3 text-[15px]">
        <label className="flex items-center gap-2">
          찍는 사람
          <input
            value={who}
            disabled={marks.length > 0}
            onChange={(e) => {
              setWho(e.target.value);
              localStorage.setItem(WHO_KEY, e.target.value);
            }}
            className="w-40 rounded border border-white/40 bg-transparent px-2 py-1"
            placeholder="여러 명이 잴 때만"
          />
        </label>
        {summary.length > 0 && (
          <details>
            <summary className="cursor-pointer">사람별 요약 ({summary.length}명)</summary>
            <div className="mt-2 flex flex-col gap-1">
              {summary.map((r) => (
                <span key={r.who} className="tabular">
                  {r.who} · {r.n}회 · 평균 오차 {r.dist.toFixed(1)}mm · 치우침 {r.dx.toFixed(1)},{" "}
                  {r.dy.toFixed(1)}mm
                </span>
              ))}
            </div>
          </details>
        )}
      </div>

      <div className="pointer-events-none relative mx-6 mt-auto mb-4 text-[17px] leading-relaxed">
        {missed === "lost"
          ? "얼굴을 놓쳐서 방금 점은 찍지 않았어요. 손이 얼굴을 가리지 않게 다시 찍어 주세요"
          : (close || missed === "close") && !done
            ? "턱까지 카메라에 들어와야 찍혀요. 허리를 펴거나 조금 뒤로 물러나 주세요"
            : saveError
              ? `저장하지 못했어요 (${saveError})`
              : saved
                ? "저장했어요. 다시를 누르고 새로 찍어 주세요"
                : done
                  ? "다 찍었어요. 초록은 찍은 자리, 빨강은 지금 계산 자리이고 숫자는 계산이 벗어난 거리(가로, 세로)예요"
                  : `주로 쓰는 눈만 뜨고 고개를 움직이지 말고, 거울에 비친 두 눈동자·코끝·입술 가운데·턱 끝·양쪽 턱 모서리를 아무 순서로 S펜으로 찍어 주세요 (${marks.length}/${TOTAL})`}
      </div>
      <div className="relative mr-6 mb-8 ml-24 flex gap-3">
        <Button
          size="lg"
          variant="outline"
          className="text-black"
          onClick={() => {
            setMarks([]);
            setSaved(false);
            setSaveError(null);
          }}
        >
          다시
        </Button>
        <Button
          size="lg"
          variant="outline"
          className="text-black"
          onClick={() => setMarks((m) => m.slice(0, -1))}
          disabled={!marks.length || saved || saving}
        >
          하나 지우기
        </Button>
        <Button size="lg" disabled={!done || saved || saving} onClick={() => void save()}>
          저장 ({savedCount}회 저장됨)
        </Button>
        <Button
          size="lg"
          variant="outline"
          className="text-black"
          disabled={!savedCount}
          onClick={() => void exportAll()}
        >
          내보내기
        </Button>
      </div>
    </main>
  );
}
