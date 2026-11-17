"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { choiceOf, userChoice, withChoice, type CheckRow, type MatchLoad } from "@/domain/check";
import type { GuideModel } from "@/domain/guide";
import {
  ExecutionMismatchError,
  executionSelections,
  faceRegistrationRequest,
  isFaceRegistrationGone,
  registerFace,
  startExecution,
} from "@/domain/guide-run";
import { runHref, useRun } from "@/domain/session";
import { ApiError, errorMessage } from "@/lib/api";
import { facePhoto } from "@/vision/face";

/**
 * 화면에 보이는 결과로 선택을 정해 서버 실행을 만든다. 매칭이 낡았으면 다시 맞추고,
 * 얼굴 등록이 없으면(404) 다시 등록하게 한다
 */
export function useStartExecution({
  guide,
  rows,
  matching,
  retry,
  onFinish,
}: {
  guide: GuideModel | null;
  rows: CheckRow[];
  matching: MatchLoad;
  /** 매칭을 다시 받는다 */
  retry: () => void;
  /** 실행을 만들었거나 얼굴을 다시 등록하게 되어 시작 확인창을 닫는다 */
  onFinish: () => void;
}) {
  const router = useRouter();
  const { run, updateRun, isCurrentRun } = useRun();
  /** 이 화면이 떠 있는지. 늦게 온 실행 생성 응답으로 다른 화면을 옮기지 않는다 */
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  /** 시작 버튼이 서버 실행을 만드는 중 · 실패한 이유 */
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = async () => {
    if (starting || !guide) return;
    const choice = rows.reduce(
      (c, r) => (userChoice(c, r.step.stepId) ? c : withChoice(c, r.step.stepId, choiceOf(r.pick))),
      run.choice,
    );
    const faceRegistrationId = run.faceRegistrationId;
    if (matching.status !== "ready" || !faceRegistrationId) {
      setError("제품 맞춰 보기가 끝나면 시작할 수 있어요.");
      return;
    }
    const runId = run.id;
    const create = (faceId: string) =>
      startExecution({
        guideId: guide.guideId,
        matchId: matching.matchId,
        faceRegistrationId: faceId,
        ...executionSelections(
          guide.steps.map((s) => s.stepId),
          choice,
        ),
      });
    // 응답을 기다리는 동안 화면을 떠났거나 실행이 바뀌었으면 결과를 쓰지 않는다
    const current = () => alive.current && isCurrentRun(runId);
    setStarting(true);
    setError(null);
    // 마지막으로 보낸 얼굴 등록. 다시 등록하면 바뀌고, 실패 원인도 이 ID로 가른다
    let faceId = faceRegistrationId;
    try {
      let executionId: string;
      try {
        executionId = await create(faceId);
      } catch (e) {
        if (!(e instanceof ExecutionMismatchError)) throw e;
        // 이 얼굴로 만든 실행이 지금 선택과 다르다: 같은 사진으로 새로 등록해 새 실행을 만든다(서버가 이전 실행을 끝낸다)
        const photo = facePhoto(runId);
        if (!photo) {
          if (!current()) return;
          onFinish();
          updateRun({ faceReg: false, faceRegistrationId: null }, runId);
          return;
        }
        const metadata = faceRegistrationRequest(guide.videoId, guide.guideId);
        faceId = (await registerFace(photo, metadata)).faceRegistrationId;
        if (current()) updateRun({ faceRegistrationId: faceId }, runId);
        executionId = await create(faceId);
      }
      if (!current()) return;
      updateRun({ choice, executionId, faceRegistrationId: faceId }, runId);
      onFinish();
      router.push(runHref("/tutorial/guide", run.guideId));
    } catch (e) {
      if (!current()) return;
      if (e instanceof ApiError && e.code === "GUIDE_MATCH_STALE") {
        retry();
        setError("제품 정보가 바뀌어 다시 맞췄어요. 확인하고 다시 시작해 주세요.");
      } else if (e instanceof ApiError && e.status === 404) {
        // 404는 얼굴 등록 · 가이드 · 매칭 어느 쪽이든 같은 코드라, 얼굴 등록을 조회해 원인을 가른다
        if (await isFaceRegistrationGone(faceId)) {
          onFinish();
          updateRun({ faceReg: false, faceRegistrationId: null }, runId);
        } else {
          retry();
          setError("가이드나 제품 매칭을 찾지 못해 다시 맞췄어요. 확인하고 다시 시작해 주세요.");
        }
      } else {
        setError(errorMessage(e));
      }
    } finally {
      setStarting(false);
    }
  };

  return { start, starting, error, clearError: () => setError(null) };
}
