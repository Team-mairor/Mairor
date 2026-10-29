"use client";

import { CameraOff, RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";

import type { CameraError, CameraErrorKind } from "./camera";

// retryable이 false면 다시 시도해도 결과가 같아 버튼을 숨긴다.
const MESSAGES: Record<CameraErrorKind, { title: string; detail: string; retryable: boolean }> = {
  insecure: {
    title: "보안 연결이 아니에요",
    detail: "카메라는 HTTPS 주소에서만 사용할 수 있어요.",
    retryable: false,
  },
  unsupported: {
    title: "카메라를 지원하지 않는 브라우저예요",
    detail: "최신 Chrome, Edge, Safari에서 다시 열어 주세요.",
    retryable: false,
  },
  "permission-denied": {
    title: "카메라 권한이 필요해요",
    detail:
      "주소창 옆 카메라 아이콘이나 브라우저 설정에서 카메라를 허용해 주세요. 기기 설정에서 브라우저의 카메라 접근도 확인해 주세요.",
    retryable: true,
  },
  blocked: {
    title: "이 화면에서는 카메라 사용이 차단되어 있어요",
    detail: "브라우저나 관리자 정책으로 카메라를 쓸 수 없어요.",
    retryable: false,
  },
  "not-found": {
    title: "카메라를 찾을 수 없어요",
    detail: "카메라가 연결되어 있는지 확인해 주세요.",
    retryable: true,
  },
  "in-use": {
    title: "카메라를 사용할 수 없어요",
    detail: "다른 앱이나 탭에서 카메라를 쓰고 있다면 종료해 주세요.",
    retryable: true,
  },
  disconnected: {
    title: "카메라 연결이 끊어졌어요",
    detail: "카메라 연결을 확인한 뒤 다시 시도해 주세요.",
    retryable: true,
  },
  "tracker-failed": {
    title: "얼굴 인식을 준비하지 못했어요",
    detail: "잠시 후 다시 시도해 주세요.",
    retryable: true,
  },
  unknown: {
    title: "카메라를 시작하지 못했어요",
    detail: "잠시 후 다시 시도해 주세요.",
    retryable: true,
  },
};

/** 다시 시도하면 달라질 수 있는 오류인지. 안내 카드도 같은 기준으로 버튼을 보여 준다 */
export function isRetryable(kind: CameraErrorKind) {
  return MESSAGES[kind].retryable;
}

export function CameraErrorView({ error, onRetry }: { error: CameraError; onRetry: () => void }) {
  const { title, detail, retryable } = MESSAGES[error.kind];

  return (
    <main
      role="alert"
      className="flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center"
    >
      <CameraOff className="size-12 text-muted-foreground" aria-hidden />
      <h1 className="text-xl font-semibold">{title}</h1>
      <p className="text-muted-foreground">{detail}</p>
      {retryable && (
        <Button size="lg" onClick={onRetry}>
          <RotateCw />
          다시 시도
        </Button>
      )}
    </main>
  );
}
