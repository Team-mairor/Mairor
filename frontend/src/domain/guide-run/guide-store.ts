import { toGuideModel, type GuideModel } from "@/domain/guide/guide-model";
import { isGuideId } from "@/domain/session";
import { ApiError, errorMessage } from "@/lib/api";

export type GuideLoad =
  | { status: "loading" }
  | { status: "ready"; guide: GuideModel; checking: boolean; error: string | null }
  | { status: "invalidId" }
  | { status: "notFound" }
  | { status: "login" }
  | { status: "invalidated"; reason: "notFound" | "versionChanged" }
  | { status: "error"; message: string };
export const LOADING: GuideLoad = { status: "loading" };
export interface GuideSnapshot {
  key: string;
  load: GuideLoad;
}
const EMPTY: GuideSnapshot = { key: "", load: LOADING };
type FetchGuide = (id: string, signal: AbortSignal) => Promise<unknown>;

/** 실행별 조회. abort와 별도로 요청 순서를 검사해 늦은 결과를 버린다. */
export class GuideStore {
  private snapshot = EMPTY;
  private listeners = new Set<() => void>();
  private sequence = 0;
  private controller: AbortController | null = null;
  private pending: Promise<boolean> | null = null;
  private guideId = "";
  constructor(
    private fetch: FetchGuide,
    private timeoutMs = 10_000,
  ) {}
  getSnapshot = () => this.snapshot;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  private publish(load: GuideLoad) {
    this.snapshot = { ...this.snapshot, load };
    this.listeners.forEach((listener) => listener());
  }
  cancel = () => {
    this.sequence++;
    this.controller?.abort();
    this.controller = null;
    this.pending = null;
  };
  activate(key: string, guideId: string) {
    this.cancel();
    this.guideId = guideId.toLowerCase();
    this.snapshot = { key, load: LOADING };
    if (!isGuideId(guideId)) {
      this.publish({ status: "invalidId" });
      return;
    }
    void this.retry();
  }
  clear() {
    this.cancel();
    this.snapshot = EMPTY;
    this.listeners.forEach((listener) => listener());
  }
  retry = (): Promise<boolean> => {
    if (this.pending) return this.pending;
    const { key, load } = this.snapshot;
    if (
      !key ||
      !isGuideId(this.guideId) ||
      load.status === "invalidated" ||
      load.status === "login"
    )
      return Promise.resolve(false);
    const previous = load.status === "ready" ? load.guide : null;
    const guideId = this.guideId;
    const request = ++this.sequence;
    const controller = new AbortController();
    this.controller = controller;
    const current = () => request === this.sequence && this.snapshot.key === key;
    this.publish(
      previous ? { status: "ready", guide: previous, checking: true, error: null } : LOADING,
    );
    let timer: ReturnType<typeof setTimeout>;
    let rejectAbort: () => void;
    const cancelled = new Promise<never>((_, reject) => {
      rejectAbort = () => reject(new DOMException("요청을 취소했습니다", "AbortError"));
      controller.signal.addEventListener("abort", rejectAbort, { once: true });
    });
    const timeout = new Promise<never>((_, reject) => {
      timer = setTimeout(() => {
        reject(new ApiError(0, "TIMEOUT", "가이드 응답이 늦어요. 다시 시도해 주세요."));
        controller.abort();
      }, this.timeoutMs);
    });
    this.pending = Promise.race([
      Promise.resolve().then(() => {
        if (controller.signal.aborted) throw new DOMException("요청을 취소했습니다", "AbortError");
        return this.fetch(guideId, controller.signal);
      }),
      timeout,
      cancelled,
    ])
      .then((raw) => {
        if (!current() || controller.signal.aborted) return false;
        const guide = toGuideModel(raw, guideId);
        if (previous && previous.guideVersion !== guide.guideVersion) {
          this.publish({ status: "invalidated", reason: "versionChanged" });
          return false;
        }
        this.publish({ status: "ready", guide: previous ?? guide, checking: false, error: null });
        return true;
      })
      .catch((error: unknown) => {
        if (!current()) return false;
        if (error instanceof ApiError && error.status === 404) {
          this.publish(
            previous ? { status: "invalidated", reason: "notFound" } : { status: "notFound" },
          );
        } else if (error instanceof ApiError && error.status === 401) {
          this.publish({ status: "login" });
        } else {
          const message =
            error instanceof ApiError
              ? errorMessage(error)
              : "가이드 내용을 읽지 못했어요. 다시 시도해 주세요.";
          this.publish(
            previous
              ? { status: "ready", guide: previous, checking: false, error: message }
              : { status: "error", message },
          );
        }
        return false;
      })
      .finally(() => {
        clearTimeout(timer);
        controller.signal.removeEventListener("abort", rejectAbort);
        if (current()) {
          this.pending = null;
          this.controller = null;
        }
      });
    return this.pending;
  };
}
