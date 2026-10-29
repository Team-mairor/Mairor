"use client";

import { ArrowLeft } from "lucide-react";
import { createContext, useContext, type ReactNode } from "react";

import {
  isRetryable,
  TRACKING_ISSUE_TEXT,
  useCamera,
  useTrackingIssue,
  type CameraErrorKind,
  type TrackingIssue,
} from "@/features/face";
import { cn } from "@/lib/utils";

interface FaceState {
  face: boolean;
  /** 공통 추적 판정. 없으면 null */
  issue: TrackingIssue | null;
}

const FaceStateContext = createContext<FaceState | null>(null);

/** 추적 상태 요약을 카메라 화면 전체가 한 번만 계산해 나눠 쓴다 (프레임 리스너 1개) */
export function FaceStateProvider({ children }: { children: ReactNode }) {
  const issue = useTrackingIssue();
  const face = issue !== "lost";
  return <FaceStateContext.Provider value={{ face, issue }}>{children}</FaceStateContext.Provider>;
}

/** 추적 상태 요약. 프레임마다가 아니라 바뀔 때만 리렌더한다 */
export function useFaceState() {
  const context = useContext(FaceStateContext);
  if (!context) throw new Error("useFaceState는 FaceStateProvider 안에서만 쓸 수 있습니다");
  return context;
}

const ERR: Partial<Record<CameraErrorKind, [string, string]>> = {
  "permission-denied": [
    "카메라 권한이 꺼져 있어요",
    "설정에서 카메라를 허용하면 내 얼굴에 입혀 볼 수 있어요.",
  ],
  "not-found": ["카메라를 찾을 수 없어요", "카메라가 연결돼 있는지 확인해 주세요."],
  "in-use": ["다른 앱이 카메라를 쓰고 있어요", "다른 앱을 닫은 뒤 다시 시도해 주세요."],
  "tracker-failed": ["얼굴 인식을 불러오지 못했어요", "네트워크를 확인하고 다시 시도해 주세요."],
  disconnected: ["카메라 연결이 끊어졌어요", "카메라 연결을 확인한 뒤 다시 시도해 주세요."],
  insecure: ["보안 연결이 아니에요", "카메라는 HTTPS 주소에서만 사용할 수 있어요."],
  unsupported: ["카메라를 지원하지 않는 브라우저예요", "최신 Chrome에서 다시 열어 주세요."],
  blocked: [
    "이 화면에서는 카메라 사용이 차단되어 있어요",
    "브라우저나 관리자 정책으로 카메라를 쓸 수 없어요.",
  ],
  unknown: ["카메라를 시작하지 못했어요", "잠시 후 다시 시도해 주세요."],
};

export type LiveAlert = "lost" | "turn" | "cover" | "far" | "light";
export const ALERT: Record<LiveAlert, [string, string]> = {
  lost: ["얼굴이 화면을 벗어났어요", "화면 가운데로 돌아오면 메이크업이 다시 보여요."],
  turn: ["고개를 정면으로 돌려 주세요", "옆으로 많이 돌리면 색이 어긋나서 잠시 숨겼어요."],
  cover: ["손이나 도구가 얼굴을 가리고 있어요", "가린 동안 메이크업을 잠시 숨겼어요."],
  far: ["조금 더 가까이 와 주세요", "얼굴이 작게 보이면 색이 정확하지 않아요."],
  light: [
    "조명이 바뀌었어요",
    "처음 등록한 얼굴보다 어두워요. 밝은 곳으로 옮기면 색이 정확해져요.",
  ],
};

/** ?alert= 값 중 아는 것만 받는다. 모르는 값은 알림 없음 */
export function parseAlert(value: string | null | undefined): LiveAlert | null {
  return value && Object.hasOwn(ALERT, value) ? (value as LiveAlert) : null;
}

export interface LiveNoteData {
  title: string;
  desc: string;
  /** 다시 시도 버튼 글자. 카메라 오류일 때만 */
  retry?: string;
  onRetry?: () => void;
  /** 카메라가 켜져 있어 인식 알림을 보여 주는 중 */
  live: boolean;
  face: boolean;
}

/** 카메라 오류 안내. 오류가 없으면 null */
function useCameraErrorNote(face: boolean): LiveNoteData | null {
  const { status, error, start } = useCamera();
  if (status !== "error" || !error) return null;
  const [t, d] = ERR[error.kind] ?? ERR.unknown!;
  // CameraErrorView와 같은 기준: 다시 시도해도 결과가 같은 오류는 버튼을 숨긴다
  const retryable = isRetryable(error.kind);
  return {
    title: t,
    desc: d,
    retry: retryable ? (error.kind === "tracker-failed" ? "다시 시도" : "카메라 켜기") : undefined,
    onRetry: retryable ? () => void start() : undefined,
    live: false,
    face,
  };
}

/** 가이드·게이지를 멈춘 이유. null이면 정상 */
export type LiveReason = LiveAlert | TrackingIssue | "error" | "starting";

export interface LiveState {
  /** 보여 줄 안내 카드. 없으면 null */
  note: LiveNoteData | null;
  /** 얼굴 위에 메이크업·가이드를 그려도 되는 상태 (카메라 준비 + 얼굴 있음 + 알림 없음) */
  canRender: boolean;
  /** 진하기를 잴 수 있는 상태 (canRender + 거리 충분) */
  canMeasure: boolean;
  reason: LiveReason | null;
}

/**
 * 현재 보여 줄 안내와 그릴 수 있는지 여부. 카메라 오류 > 준비 중 > 확인용 알림 > 추적 문제.
 * 세 카메라 화면(미리보기·제품 체크·튜토리얼)은 이 값으로 숨김·측정 불가를 판단한다 (CAMERA-004)
 */
export function useLiveState(
  alert?: LiveAlert | null,
  /** 화면별 추가 판정. 공통 추적 판정에 문제가 없을 때만 쓴다 */
  extraIssue?: TrackingIssue | null,
): LiveState {
  const { status } = useCamera();
  const { face, issue: trackIssue } = useFaceState();
  const issue = trackIssue ?? extraIssue ?? null;
  const err = useCameraErrorNote(face);
  const off = { canRender: false, canMeasure: false };
  if (err) return { note: err, ...off, reason: "error" };
  if (status !== "ready")
    return {
      note: { title: "카메라를 켜는 중이에요", desc: "잠시만 기다려 주세요.", live: false, face },
      ...off,
      reason: "starting",
    };
  if (alert)
    return {
      note: { title: ALERT[alert][0], desc: ALERT[alert][1], live: true, face },
      // 실제 거리 감지와 같은 기준: 멀 때는 화장·가이드를 두고 측정만 멈춘다
      canRender: alert === "far",
      canMeasure: false,
      reason: alert,
    };
  if (issue)
    return {
      note: { ...TRACKING_ISSUE_TEXT[issue], live: true, face },
      // 너무 멀 때만 그리고, 나머지는 가이드·화장을 숨긴 상태다
      canRender: issue === "far",
      canMeasure: false,
      reason: issue,
    };
  return { note: null, canRender: true, canMeasure: true, reason: null };
}

/** 안내 카드만 필요할 때 */
export function useLiveNote(alert?: LiveAlert | null): LiveNoteData | null {
  return useLiveState(alert).note;
}

/** 좌상단 LIVE 표시 */
export function LiveTag({ className }: { className?: string }) {
  const { status } = useCamera();
  const { face } = useFaceState();
  return (
    <span
      className={cn(
        "flex h-12 items-center gap-2.5 rounded-full border border-white/15 bg-[rgba(42,10,28,.78)] py-0 pr-[18px] pl-3.5 font-label text-[15px] font-bold tracking-[.14em] text-white",
        className,
      )}
    >
      <span
        className={cn("size-2.5 rounded-full", face ? "bg-lime" : "bg-rose")}
        style={{ animation: "mr-pulse 1.4s ease-out infinite" }}
      />
      {status === "ready" ? "LIVE" : "CAMERA"}
    </span>
  );
}

/** 카메라 오류일 때만 안내 카드를 보여 준다. 인식 알림을 따로 쓰지 않는 화면용 */
export function CameraErrorNote({ className }: { className?: string }) {
  const { face } = useFaceState();
  const note = useCameraErrorNote(face);
  return <LiveNote note={note} className={className} />;
}

/** 상단 안내 카드 (카메라 오류·인식 알림) */
export function LiveNote({ note, className }: { note: LiveNoteData | null; className?: string }) {
  if (!note) return null;
  return (
    <div
      role="status"
      className={cn(
        "absolute inset-x-5 top-[84px] z-[2] flex animate-fade items-center gap-[18px] rounded-3xl border border-white/15 bg-[rgba(42,10,28,.9)] px-[22px] py-[18px] text-white",
        className,
      )}
    >
      <span className="size-3 shrink-0 rounded-full bg-rose" />
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <span className="text-[22px] leading-[1.3] font-bold text-pretty">{note.title}</span>
        <span className="text-[17px] leading-[1.5] text-pretty text-line-2">{note.desc}</span>
      </div>
      {note.retry && (
        <button
          type="button"
          onClick={note.onRetry}
          className="flex h-[52px] shrink-0 items-center rounded-full bg-white px-[22px] text-[17px] font-bold whitespace-nowrap text-ink-deep active:scale-[.97]"
        >
          {note.retry}
        </button>
      )}
    </div>
  );
}

/** 하단 반투명 패널 */
export function GlassPanel({
  children,
  className,
  coversFace = true,
}: {
  children: ReactNode;
  className?: string;
  /** 패널 뒤 얼굴 부위를 화면 밖으로 판정할지. 화면을 거의 덮는 시트는 false */
  coversFace?: boolean;
}) {
  const { setCoverPanel } = useCamera();
  return (
    <div
      ref={coversFace ? setCoverPanel : undefined}
      className={cn(
        "absolute inset-x-4 bottom-4 flex flex-col gap-5 rounded-[36px] border border-white/10 bg-[rgba(42,10,28,.92)] px-7 pt-6 pb-[18px] text-white shadow-[0_24px_60px_rgba(20,4,12,.45)] backdrop-blur-2xl",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** 패널 안 동그란 뒤로 버튼 */
export function RoundBack({
  onClick,
  label = "뒤로",
  className,
}: {
  onClick: () => void;
  label?: string;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className={cn(
        "flex size-[72px] shrink-0 items-center justify-center rounded-full border border-white/15 bg-white/8 text-white hover:bg-white/15 active:scale-[.95]",
        className,
      )}
    >
      <ArrowLeft className="size-[26px]" strokeWidth={2.2} aria-hidden />
    </button>
  );
}
