"use client";

import { useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { facePhoto } from "@/features/face";
import { isRunPath, runHref, useSession, type RunRouteAction } from "@/features/session";
import { GuideStatus } from "@/features/tutorial";

import { useGuide } from "./use-guide";

/** 실행 화면 본문보다 먼저 진입·조회·인증을 검사한다 */
export function RunGuideBoundary({
  path,
  initialized,
  action,
  children,
}: {
  path: string;
  initialized: boolean;
  action: RunRouteAction | null;
  children: ReactNode;
}) {
  const { state, endRun } = useSession();
  const { load, retry } = useGuide();
  const router = useRouter();
  const run = state.run;
  const home = {
    label: "홈으로",
    onClick: () => {
      endRun(run.id);
      router.push("/home");
    },
  };
  if (!isRunPath(path)) return children;
  if (!initialized) return <GuideStatus title="준비 상태를 확인하고 있어요" />;
  if (!state.loggedIn)
    return (
      <GuideStatus
        title="로그인이 필요해요"
        action={{ label: "로그인하기", onClick: () => router.push("/login") }}
      />
    );
  if (action?.kind === "invalidId")
    return <GuideStatus title="가이드 주소가 올바르지 않아요" action={home} />;
  if (action?.kind !== "allow") return <GuideStatus title="처음부터 준비하고 있어요" />;
  if (run.mode !== "guide") return children;
  if (run.phase === "invalidated" || load.status === "invalidated")
    return (
      <GuideStatus
        title="이 가이드를 더 이상 이용할 수 없어요"
        body="진행을 멈췄어요. 홈에서 가이드를 다시 선택해 처음부터 시작해 주세요."
        action={home}
      />
    );
  switch (load.status) {
    case "loading":
      return <GuideStatus title="가이드를 불러오고 있어요" />;
    case "invalidId":
      return <GuideStatus title="가이드 주소가 올바르지 않아요" action={home} />;
    case "notFound":
      return (
        <GuideStatus
          title="가이드가 없거나 아직 이용할 수 없어요"
          body="검수가 끝난 가이드만 따라 할 수 있어요."
          action={home}
        />
      );
    case "login":
      return <GuideStatus title="로그인이 필요해요" action={home} />;
    case "error":
      return (
        <GuideStatus
          title="가이드를 불러오지 못했어요"
          body={load.message}
          action={{
            label: "다시 시도",
            onClick: () => {
              void retry();
            },
          }}
        />
      );
    case "ready":
      break;
  }
  if (run.guideVersion !== load.guide.guideVersion)
    return <GuideStatus title="가이드를 확인하고 있어요" />;
  if (!load.guide.steps.length)
    return <GuideStatus title="따라 할 단계가 없는 가이드예요" action={home} />;
  if (path !== "/loading" && run.phase !== "completed" && !facePhoto(run.id))
    return <GuideStatus title="얼굴을 다시 등록해 주세요" />;
  // 연결 전인 미리보기는 샘플 대신 안내를 보여 준다
  if (path === "/preview")
    return (
      <GuideStatus
        title="미리보기를 아직 이용할 수 없어요"
        body="제품 확인은 계속할 수 있어요."
        action={{
          label: "제품 확인으로",
          onClick: () => router.push(runHref("/check", run.guideId)),
        }}
      />
    );
  const paused = load.checking || !!load.error;
  return (
    <>
      <div className="relative flex min-h-0 flex-1 flex-col" inert={paused}>
        {children}
      </div>
      {paused && (
        <div className="fixed inset-0 z-50 flex flex-col bg-night/95 text-white">
          <GuideStatus
            title={
              load.checking ? "가이드를 다시 확인하고 있어요" : "가이드 확인을 마치지 못했어요"
            }
            body={load.error ?? undefined}
            action={
              load.checking
                ? undefined
                : {
                    label: "다시 확인",
                    onClick: () => {
                      void retry();
                    },
                  }
            }
          />
          <button type="button" className="mb-10 text-white underline" onClick={home.onClick}>
            홈으로
          </button>
        </div>
      )}
    </>
  );
}
