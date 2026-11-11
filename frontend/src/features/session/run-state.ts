import type { VideoItem } from "@/features/video";

/** auto는 실제 가이드 제품 체크가 시작할 때 매칭 결과로 채운 선택. 다시 체크하면 새 매칭 결과를 쓴다 */
export type Choice = ({ kind: "none" } | { kind: "pouch"; id: string }) & { auto?: true };
export type RunPhase = "preparing" | "tutorial" | "completed" | "invalidated";

export interface RunState {
  id: string;
  mode: "guide" | "sample" | null;
  guideId: string | null;
  guideVersion: number | null;
  phase: RunPhase;
  picked: VideoItem | null;
  replay: "guide" | "report" | null;
  /** 이 실행이 요청한 분석 작업. 로딩 화면은 주소의 jobId와 같을 때만 picked를 쓴다 */
  jobId: string | null;
  faceReg: boolean;
  /** 가이드 실행에서 서버에 등록한 얼굴. 샘플 실행은 늘 null */
  faceRegistrationId: string | null;
  /** 제품 체크에서 시작한 서버 실행. 동의 · 나가기 · 완료가 이 ID로 간다 */
  executionId: string | null;
  choice: Record<string, Choice>;
  subOn: Record<string, boolean>;
  photoOk: boolean;
  captures: string[];
}

export const EMPTY_RUN: RunState = {
  id: "",
  mode: null,
  guideId: null,
  guideVersion: null,
  phase: "preparing",
  picked: null,
  replay: null,
  jobId: null,
  faceReg: false,
  faceRegistrationId: null,
  executionId: null,
  choice: {},
  subOn: {},
  photoOk: false,
  captures: [],
};

export type StartRunInput =
  | { kind: "guide"; guideId: string; replay?: "guide" | "report" }
  | {
      kind: "sample";
      picked?: VideoItem;
      replay?: "guide" | "report" | null;
      jobId?: string | null;
    };

export type RunPatch = Partial<
  Pick<
    RunState,
    "faceReg" | "faceRegistrationId" | "executionId" | "choice" | "subOn" | "photoOk" | "captures"
  >
>;

/** 얼굴 등록을 마쳤나. 가이드 실행은 서버 등록 ID까지 있어야 한다 */
export function faceReady(run: RunState) {
  return run.faceReg && (run.mode !== "guide" || run.faceRegistrationId !== null);
}

export function createRun(input: StartRunInput, id: string): RunState {
  return {
    ...EMPTY_RUN,
    id,
    mode: input.kind,
    guideId: input.kind === "guide" ? input.guideId.toLowerCase() : null,
    replay: input.replay ?? (input.kind === "guide" ? "guide" : null),
    picked: input.kind === "sample" ? (input.picked ?? null) : null,
    jobId: input.kind === "sample" ? (input.jobId ?? null) : null,
  };
}

export function invalidateRun(run: RunState): RunState {
  return {
    ...EMPTY_RUN,
    id: run.id,
    mode: run.mode,
    guideId: run.guideId,
    guideVersion: run.guideVersion,
    phase: "invalidated",
  };
}

export const isGuideId = (id: unknown): id is string =>
  typeof id === "string" &&
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id);

export function runHref(path: string, guideId: string | null, extra?: Record<string, string>) {
  const [pathname, search = ""] = path.split("?");
  const params = new URLSearchParams(search);
  if (guideId !== null) params.set("guideId", guideId.toLowerCase());
  for (const [key, value] of Object.entries(extra ?? {}))
    if (key !== "guideId") params.set(key, value);
  return pathname + (params.size ? `?${params}` : "");
}

export const isRunPath = (path: string) =>
  ["/loading", "/preview", "/check", "/tutorial/guide", "/tutorial", "/done"].includes(path);

export type RunRouteAction =
  | { kind: "allow" }
  | { kind: "invalidId" }
  | { kind: "start"; guideId: string }
  | { kind: "redirect"; href: string };

/** URL은 새 실행의 입력이다. 화면 전환 중에만 메모리의 run을 이어 쓴다. */
export function runRouteAction(path: string, search: string, run: RunState): RunRouteAction {
  if (!isRunPath(path)) return { kind: "allow" };
  const params = new URLSearchParams(search);
  const ids = params.getAll("guideId");
  if (ids.length > 1 || (ids.length === 1 && !isGuideId(ids[0]))) return { kind: "invalidId" };
  const id = ids[0]?.toLowerCase();
  if (id && (run.mode !== "guide" || run.guideId !== id || !run.id))
    return { kind: "start", guideId: id };
  if (!run.id) return { kind: "redirect", href: "/select" };
  if (run.mode !== "guide") return { kind: "allow" };
  if (!id)
    return { kind: "redirect", href: runHref(path + (search ? `?${search}` : ""), run.guideId) };
  if (run.phase === "invalidated") return { kind: "allow" };
  // 완료 화면은 얼굴 등록과 상관없이 연다
  if (run.phase === "completed")
    return path === "/done" ? { kind: "allow" } : { kind: "redirect", href: runHref("/done", id) };
  if (path !== "/loading" && !faceReady(run))
    return { kind: "redirect", href: runHref("/loading", id) };
  // 가이드 실행은 제품 체크에서 서버 실행을 만든 뒤에만 안내 · 튜토리얼로 간다
  if ((path === "/tutorial" || path === "/tutorial/guide") && !run.executionId)
    return { kind: "redirect", href: runHref("/check", id) };
  if (path === "/tutorial" && run.phase === "preparing")
    return { kind: "redirect", href: runHref("/tutorial/guide", id) };
  // 완료하지 않은 실행은 완료 화면을 열지 않는다
  if (path === "/done") return { kind: "redirect", href: runHref("/loading", id) };
  return { kind: "allow" };
}
