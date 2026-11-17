"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import {
  deleteFaceRegistration,
  faceRegistrationRequest,
  registerFace,
  useGuide,
} from "@/domain/guide-run";
import { faceReady, runHref, useRun, useSessionActions } from "@/domain/session";
import {
  ApiError,
  errorMessage,
  type AnalysisJobStatus,
  type FaceRegistrationRequest,
} from "@/lib/api";
import { facePhoto, useCamera } from "@/vision/face";

import type { Fail, Review } from "./loading-status";

/**
 * 로딩 화면의 얼굴 등록. 분석 중에 등록을 처음 권하고, 등록 사진을 서버에 저장한다.
 * 새로고침하면 메모리 사진이 사라지므로 다시 등록한다
 */
export function useFaceFlow({
  replay,
  activeJobId,
  job,
  pct,
  fail,
  review,
  openPouch,
}: {
  /** 분석 없이 이미 있는 가이드로 시작한다 */
  replay: boolean;
  activeJobId: string | null;
  job: AnalysisJobStatus | null;
  pct: number;
  fail: Fail;
  review: Review;
  /** 얼굴 등록을 마치면 파우치 확인을 이어서 연다 */
  openPouch: () => void;
}) {
  const router = useRouter();
  const { run, updateRun, isCurrentRun } = useRun();
  const { expireSession } = useSessionActions();
  const camera = useCamera();
  const { load } = useGuide();

  const faceOk = faceReady(run) && facePhoto(run.id) !== null;
  const captured = run.faceReg && facePhoto(run.id) !== null;
  // 다시 따라 하기는 들어오자마자 등록부터 한다. 이미 등록했으면 다시 띄우지 않는다
  const [modal, setModal] = useState(replay && !captured && !run.facePrompted);
  const [shown, setShown] = useState(replay || run.facePrompted);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const savingRef = useRef(false);

  // 실제 분석은 대기열부터 준비한다. 처음 한 번만 등록을 권한다
  useEffect(() => {
    const preparing = activeJobId ? job && ["PENDING", "RUNNING"].includes(job.status) : false;
    if (preparing && !shown && !captured && !fail && !review) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- 준비를 처음 권하는 순간 한 번만
      setShown(true);
      setModal(true);
      updateRun({ facePrompted: true }, run.id);
    }
  }, [pct, activeJobId, job, shown, captured, fail, review, updateRun, run.id]);

  const saveFace = async (photo: Blob, metadata: FaceRegistrationRequest) => {
    try {
      return await registerFace(photo, metadata);
    } catch (e) {
      if (isCurrentRun(run.id) && e instanceof ApiError && e.code === "UNAUTHORIZED") {
        expireSession();
        router.replace("/login?expired=basic");
      }
      throw e;
    }
  };

  /** 화면을 떠났거나 실행이 바뀐 뒤에 끝난 등록은 서버에서 지운다 */
  const discard = (faceRegistrationId: string) =>
    deleteFaceRegistration(faceRegistrationId).catch((e: unknown) =>
      console.warn("얼굴 등록 정리 실패", e),
    );

  /** 등록 창을 연다 */
  const open = () => {
    setShown(true);
    updateRun({ facePrompted: true }, run.id);
    setModal(true);
  };

  /** 나중에 하기 */
  const later = () => {
    setModal(false);
    setShown(true);
    updateRun({ facePrompted: true }, run.id);
    if (!run.pouchReviewed) openPouch();
    camera.stop();
  };

  /** 등록 사진을 서버에 저장하고 등록 ID를 실행에 남긴다 */
  const register = async () => {
    let faceRegistrationId: string | null = null;
    const metadata =
      activeJobId && job
        ? faceRegistrationRequest(job.videoId, null)
        : run.mode === "guide" && load.status === "ready"
          ? faceRegistrationRequest(load.guide.videoId, load.guide.guideId)
          : null;
    if (activeJobId || run.mode === "guide") {
      const photo = facePhoto(run.id);
      if (!metadata || !photo) throw new Error("영상이나 얼굴 사진이 없다");
      faceRegistrationId = (await saveFace(photo, metadata)).faceRegistrationId;
      if (!isCurrentRun(run.id)) {
        await discard(faceRegistrationId);
        return;
      }
    }
    if (!isCurrentRun(run.id)) return;
    updateRun({ faceReg: true, facePrompted: true, faceRegistrationId }, run.id);
    setShown(true);
    setModal(false);
    if (!run.pouchReviewed) openPouch();
  };

  /** 촬영은 끝났지만 서버 저장이 안 된 등록을 다시 저장하고 미리보기로 간다 */
  const savePrepared = async () => {
    if (savingRef.current || load.status !== "ready") return;
    const photo = facePhoto(run.id);
    if (!photo) return;
    savingRef.current = true;
    setSaving(true);
    setSaveError(null);
    try {
      const metadata = faceRegistrationRequest(load.guide.videoId, load.guide.guideId);
      const { faceRegistrationId } = await saveFace(photo, metadata);
      if (!isCurrentRun(run.id)) {
        await discard(faceRegistrationId);
        return;
      }
      updateRun({ faceRegistrationId }, run.id);
      router.push(runHref("/check", run.guideId));
    } catch (e) {
      if (!isCurrentRun(run.id)) return;
      setSaveError(`얼굴 등록을 저장하지 못했어요. ${errorMessage(e)}`);
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  return { ok: faceOk, captured, modal, saving, saveError, open, later, register, savePrepared };
}
