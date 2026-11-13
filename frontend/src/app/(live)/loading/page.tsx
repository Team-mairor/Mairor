"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { FlowSteps } from "@/components/flow-steps";
import { IconButton } from "@/components/ui/icon-button";
import { PillButton } from "@/components/ui/pill-button";
import { facePhoto, useCamera, useHiddenVideo } from "@/features/face";
import {
  faceRegistrationRequest,
  deleteFaceRegistration,
  registerFace,
  useGuide,
  useRunQuery as useQuery,
} from "@/features/guide";
import {
  AnalysisProgress,
  FaceRegisterModal,
  FoundProducts,
  jobFailure,
  jobReview,
  PouchCheckModal,
  ReadyStatus,
  retryAnalysisJob,
  ScanPreview,
  stageText,
  useAnalysisJob,
} from "@/features/loading";
import { emptyDraft, ProductSheet, type PouchCat, type ProductDraft } from "@/features/pouch";
import { faceReady, hasSame, isGuideId, runHref, useSession } from "@/features/session";
import { ANALYSIS_PHASES } from "@/features/video";
import {
  ApiError,
  errorMessage,
  type AnalysisJobStatus,
  type FaceRegistrationRequest,
} from "@/lib/api";
import { REF_PRODUCTS, VIDEOS } from "@/mocks/mock-data";

const PHASE_EN = ["Queued", "Fetching", "Scenes", "Detecting", "Steps", "Composing"];

function partLabel(part: string | null) {
  if (!part) return "기타";
  return (
    (
      {
        foundation: "파운데이션",
        eyeshadow: "아이섀도",
        eyeliner: "아이라이너",
        blush: "블러셔",
        lip: "립",
        brow: "브로우",
        mascara: "마스카라",
        contour: "컨투어",
        highlight: "하이라이터",
        other: "기타",
      } as Record<string, string>
    )[part] ?? part
  );
}

function pouchCategory(part?: string): PouchCat {
  const value = (part ?? "").toLowerCase();
  if (value.includes("foundation") || value.includes("파운데이션") || value.includes("베이스")) {
    return "베이스";
  }
  if (
    ["eyeshadow", "eyeliner", "mascara"].some((partName) => value.includes(partName)) ||
    /아이섀도|아이라이너|마스카라|아이/.test(value)
  ) {
    return "아이";
  }
  if (value.includes("brow") || value.includes("브로우")) return "브로우";
  if (
    ["blush", "contour", "highlight"].some((partName) => value.includes(partName)) ||
    /블러셔|컨투어|하이라이터|치크/.test(value)
  ) {
    return "치크";
  }
  if (value.includes("lip") || value.includes("립")) return "립";
  return "도구";
}

/** i번째 제품을 찾았다고 보여 줄 진행률. 단계 수와 상관없이 6~90% 사이에 고르게 나눈다 */
const foundAt = (i: number) => 6 + (i * 84) / REF_PRODUCTS.length;

/** timeout·failed는 샘플, stopped는 실제 작업 FAILED, missing은 열 수 없는 작업 */
type Fail = null | "timeout" | "failed" | "stopped" | "missing";
type Review = null | "pending" | "rejected";

/** 로그인 만료(401)가 아닌 오류는 열 수 없는 작업으로 본다 */
function jobFail(error: ApiError | null, job: AnalysisJobStatus | null): Fail {
  if (error && error.code !== "UNAUTHORIZED") return "missing";
  if (job?.status === "FAILED") return "stopped";
  return null;
}

/**
 * 04 로딩 · 준비. ?jobId=면 그 분석 작업 상태를 받고, 없으면 샘플로 움직인다.
 * 샘플 상태: ?joined=1 · ?fail=timeout|failed · ?review=pending|rejected
 */
export default function LoadingPage() {
  const query = useQuery();
  // 주소를 읽은 뒤 그린다. jobId가 바뀌면 이전 작업의 진행률·모달 상태를 버리고 새로 시작한다
  if (!query) return null;
  const jobId = query.get("jobId");
  return <LoadingScreen key={jobId ?? ""} query={query} jobId={jobId} />;
}

function LoadingScreen({ query, jobId }: { query: URLSearchParams; jobId: string | null }) {
  const router = useRouter();
  const { state, update, updateRun, isCurrentRun, expireSession } = useSession();
  const camera = useCamera();
  const { load } = useGuide();
  const run = state.run;
  // 실제 작업에는 이전 실행의 '분석 없이 시작'이 섞이지 않게 한다
  const replay = !jobId && !!run.replay;
  const sample = !jobId;
  // 상태 응답에 영상 정보가 없어, 이 작업으로 시작한 실행의 영상만 쓰고 모르면 비워 둔다
  const picked = jobId ? (run.jobId === jobId ? run.picked : null) : (run.picked ?? VIDEOS[0]);
  const href = (path: string) => runHref(path, run.guideId);
  // 새로고침하면 메모리 사진이 사라지므로 다시 등록한다.
  const faceOk = faceReady(run) && facePhoto(run.id) !== null;
  const faceCaptured = run.faceReg && facePhoto(run.id) !== null;

  const [demoPct, setDemoPct] = useState(0);
  const [joined, setJoined] = useState(false);
  const [demoFail, setDemoFail] = useState<Fail>(null);
  const [demoReview, setDemoReview] = useState<Review>(null);
  const [faceModal, setFaceModal] = useState(replay && !faceCaptured && !run.facePrompted);
  const [faceShown, setFaceShown] = useState(replay || run.facePrompted);
  const [pouchModal, setPouchModal] = useState(false);
  const [newIds, setNewIds] = useState<string[]>([]);
  const [form, setForm] = useState<ProductDraft | null>(null);
  // 실제 작업 다시 시도: 요청 중 · 실패 문구 · 서버가 다시 시도할 수 없다고 한 작업
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);
  const [retryRefused, setRetryRefused] = useState(false);
  const [savingFace, setSavingFace] = useState(false);
  const [faceSaveError, setFaceSaveError] = useState<string | null>(null);
  const faceSaving = useRef(false);

  useEffect(() => {
    if (run.mode === "guide") return;
    if (query.get("joined")) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- 주소로 받은 상태를 한 번 반영한다
      setJoined(true);
      setDemoPct(46);
    }
    const f = query.get("fail");
    if (f === "timeout" || f === "failed") {
      setDemoFail(f);
      setDemoPct(38);
      setFaceShown(true);
    }
    const r = query.get("review");
    if (r === "pending" || r === "rejected") {
      setDemoReview(r);
      setDemoPct(100);
      setFaceShown(true);
    }
  }, [query, run.mode]);

  const live = useAnalysisJob(jobId);
  const job = jobId ? live.job : null;
  const pct = jobId ? live.pct : replay ? 100 : demoPct;
  const fail = jobId ? jobFail(live.error, job) : demoFail;
  const review: Review = job ? jobReview(job) : demoReview;
  // 분석이 끝나 공개되면 그 가이드로 바로 넘어간다. 옛 검수 대기 작업은 상태를 계속 받다가 승인되면 넘어간다
  const approvedGuide =
    job?.status === "COMPLETED" && job.reviewStatus === "APPROVED" && isGuideId(job.guideId)
      ? job.guideId
      : null;

  useEffect(() => {
    if (live.error?.code === "UNAUTHORIZED") {
      expireSession();
      router.replace("/login?expired=basic");
    }
  }, [live.error, expireSession, router]);

  // 샘플 진행률 타이머
  const running = !replay && !fail && pct < 100;
  useEffect(() => {
    if (!running || !sample) return;
    const t = setInterval(() => setDemoPct((p) => Math.min(100, p + 1)), 600);
    return () => clearInterval(t);
  }, [running, sample]);

  // 실제 분석은 대기열부터, 샘플은 4%부터 준비한다.
  useEffect(() => {
    const preparing = jobId ? job && ["PENDING", "RUNNING"].includes(job.status) : pct >= 4;
    if (preparing && !faceShown && !faceCaptured && !fail && !review) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- 준비를 처음 권하는 순간 한 번만
      setFaceShown(true);
      setFaceModal(true);
      updateRun({ facePrompted: true }, run.id);
    }
  }, [pct, jobId, job, faceShown, faceCaptured, fail, review, updateRun, run.id]);

  // 카메라 영상은 등록 모달 안에서만 보여 준다.
  useHiddenVideo();

  const done = pct >= 100;
  const phaseIdx = done ? 6 : ANALYSIS_PHASES.filter((p) => pct >= p[2]).length - 1;
  const pi = Math.max(0, Math.min(5, phaseIdx));
  const phaseName = ANALYSIS_PHASES[pi][1];
  const phaseLabel = fail
    ? fail === "missing"
      ? "작업을 찾지 못했어요"
      : `${phaseName} 단계에서 멈췄어요`
    : done
      ? review === "pending"
        ? "분석 완료 · 검수 대기"
        : review === "rejected"
          ? "이용할 수 없음"
          : "분석이 끝났어요"
      : jobId
        ? (stageText(job?.stageProgress ?? null) ?? phaseName)
        : `${phaseName} 중…`;
  const phaseEn = fail ? "Stopped." : done ? (review ? "In review." : "Ready.") : PHASE_EN[pi];
  // 실제 작업은 남은 시간을 받지 못한다(estimatedRemainingSeconds가 늘 null)
  const eta = fail
    ? "멈춤"
    : done
      ? "완료"
      : jobId
        ? "처리 중"
        : `약 ${Math.ceil((100 - pct) * 0.6)}초 남음`;
  const scanSec = Math.floor(pct * 7.5);
  const scanTime = `${Math.floor(scanSec / 60)}:${String(scanSec % 60).padStart(2, "0")}`;

  // 실제 작업은 상태 응답의 단계별 제품 결과를 표시한다
  const rows =
    sample && run.mode !== "guide"
      ? REF_PRODUCTS.map((r, i) => ({
          ...r,
          found: pct >= foundAt(i),
          next: pct < foundAt(i) && (i === 0 || pct >= foundAt(i - 1)),
          have: r.have || hasSame(r, state.pouch),
        }))
      : (job?.foundProducts ?? []).map((product, i) => ({
          id: `${product.stepId ?? "product"}-${i}`,
          cat: partLabel(product.part),
          color: "#EADDE0",
          found: true,
          next: false,
          have: product.ownership === "OWNED",
          name: product.referenceProduct.name,
          productName: product.referenceProduct.name,
        }));
  const foundCount = rows.filter((r) => r.found).length;
  const haveCount = rows.filter((r) => r.have).length;

  const notice = fail
    ? {
        timeout: {
          tag: "STOPPED · TIMEOUT",
          title: "분석이 너무 오래 걸려 멈췄어요",
          sub: `${phaseName} 단계에서 멈췄어요. 다시 시도하면 이 단계부터 이어서 분석해요.`,
          retry: true,
        },
        failed: {
          tag: "STOPPED · FAILED",
          title: "이 영상은 분석할 수 없어요",
          sub: `${phaseName} 단계에서 메이크업 장면을 찾지 못했어요. 다른 영상을 골라 주세요.`,
          retry: false,
        },
        stopped: job
          ? jobFailure(retryRefused ? { ...job, retryable: false } : job, phaseName)
          : {
              tag: "STOPPED",
              title: "분석을 마치지 못했어요",
              sub: `${phaseName} 단계에서 멈췄어요. 다른 영상을 골라 주세요.`,
              retry: false,
            },
        missing: {
          tag: "NOT FOUND",
          title: "분석 작업을 찾을 수 없어요",
          sub: "주소를 다시 확인하거나 다른 영상을 골라 주세요.",
          retry: false,
        },
      }[fail]
    : review === "pending"
      ? {
          tag: "IN REVIEW",
          title: "분석은 끝났고, 검수 중이에요",
          // 고른 영상을 모르면 홈 카드를 만들 수 없어 홈 안내를 뺀다
          sub: picked
            ? "검수를 통과한 가이드만 따라 할 수 있어요. 검수가 끝나면 홈에서 바로 시작할 수 있어요."
            : "검수를 통과한 가이드만 따라 할 수 있어요.",
          retry: false,
        }
      : review === "rejected"
        ? {
            tag: "REJECTED",
            title: "이 영상은 가이드로 쓸 수 없어요",
            sub: "이 영상의 가이드는 내려졌어요. 다른 영상을 골라 주세요.",
            retry: false,
          }
        : approvedGuide
          ? {
              tag: "READY",
              title: "분석이 끝났어요",
              sub: "이 영상의 가이드로 바로 따라 할 수 있어요.",
              retry: false,
            }
          : null;

  const guideOk = approvedGuide
    ? true
    : run.mode === "guide"
      ? load.status === "ready"
      : replay || (done && !notice);
  const guideState = fail
    ? "멈춤"
    : review
      ? review === "pending"
        ? "검수 대기"
        : "이용 불가"
      : approvedGuide
        ? "준비 완료"
        : guideOk
          ? "완료"
          : `분석 중 ${pct}%`;

  let ctaLabel = "";
  let ctaGo: (() => void) | null = null;
  if (approvedGuide) {
    ctaLabel = "가이드로 따라 하기";
    // 실행 전환은 주소 변경 뒤 Provider가 처리한다.
    ctaGo = () => router.push(runHref("/loading", approvedGuide, jobId ? { jobId } : undefined));
  } else if (review === "pending") {
    ctaLabel = "홈으로";
    ctaGo = () => {
      if (picked) {
        update({ pendingGuide: { title: picked.title, ytid: picked.ytid, status: "pending" } });
      }
      router.push("/home");
    };
  } else if (review === "rejected") {
    ctaLabel = "다른 영상 고르기";
    ctaGo = () => router.push("/select");
  } else if (!guideOk) ctaLabel = "분석이 끝나면 미리보기를 열 수 있어요";
  else if (!faceCaptured) {
    // 실제 가이드는 색상 정보가 없어 입혀 볼 수 없다
    const tryOn = replay && run.mode !== "guide";
    ctaLabel = tryOn ? "얼굴 등록하고 입혀보기" : "얼굴 등록하고 미리보기";
    ctaGo = () => {
      setFaceShown(true);
      updateRun({ facePrompted: true }, run.id);
      setFaceModal(true);
    };
  } else if (!faceOk && run.mode === "guide") {
    ctaLabel = savingFace
      ? "얼굴 등록을 저장하는 중"
      : faceSaveError
        ? "얼굴 등록 저장 다시 시도"
        : "미리보기 보기";
    ctaGo = savingFace
      ? null
      : () => {
          void savePreparedFace();
        };
  } else {
    ctaLabel = replay && run.mode !== "guide" ? "입혀보기" : "미리보기 보기";
    ctaGo = () => router.push(href("/preview"));
  }

  const barText = replay
    ? run.replay === "guide"
      ? "분석해 둔 가이드가 있어 바로 시작해요"
      : "이전에 분석한 가이드를 그대로 써요"
    : done
      ? "영상 분석이 끝났어요"
      : "영상 분석은 그대로 진행 중이에요";

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

  const savePreparedFace = async () => {
    if (faceSaving.current || load.status !== "ready") return;
    const photo = facePhoto(run.id);
    if (!photo) return;
    faceSaving.current = true;
    setSavingFace(true);
    setFaceSaveError(null);
    try {
      const metadata = faceRegistrationRequest(load.guide.videoId, load.guide.guideId);
      const { faceRegistrationId } = await saveFace(photo, metadata);
      if (!isCurrentRun(run.id)) {
        await deleteFaceRegistration(faceRegistrationId).catch((e: unknown) =>
          console.warn("얼굴 등록 정리 실패", e),
        );
        return;
      }
      updateRun({ faceRegistrationId }, run.id);
      router.push(href("/preview"));
    } catch (e) {
      if (!isCurrentRun(run.id)) return;
      setFaceSaveError(`얼굴 등록을 저장하지 못했어요. ${errorMessage(e)}`);
    } finally {
      faceSaving.current = false;
      setSavingFace(false);
    }
  };

  const retryJob = async () => {
    if (!jobId || retrying) return;
    setRetrying(true);
    setRetryError(null);
    try {
      const next = await retryAnalysisJob(jobId);
      if (next.jobId === jobId) {
        live.restart(next);
        return;
      }
      // 재시도 합류에도 촬영 상태를 유지한다.
      updateRun({ jobId: next.jobId }, run.id);
      router.replace(`/loading?jobId=${encodeURIComponent(next.jobId)}`);
    } catch (e) {
      if (e instanceof ApiError && e.code === "UNAUTHORIZED") {
        expireSession();
        router.replace("/login?expired=basic");
        return;
      }
      // 서버가 다시 시도할 수 없다고 하면 버튼을 거두고, 안내 문구가 이미 다른 영상을 권하므로 이유만 짧게
      if (e instanceof ApiError && e.code === "ANALYSIS_NOT_RETRYABLE") {
        setRetryRefused(true);
        setRetryError("이 분석은 다시 시도할 수 없어요.");
        return;
      }
      setRetryError(errorMessage(e));
    } finally {
      setRetrying(false);
    }
  };

  const closePouch = () => {
    setPouchModal(false);
    updateRun({ pouchReviewed: true }, run.id);
    if (replay && faceOk) router.push(href("/preview"));
  };

  return (
    <main className="relative flex min-h-(--screen-h) flex-1 flex-col bg-white text-ink">
      <header className="flex h-16 shrink-0 items-center gap-3.5 border-b border-line px-8">
        <IconButton
          size={44}
          onClick={() => router.push("/select")}
          title="영상 입력"
          aria-label="영상 입력"
        />
        <span className="font-serif text-[28px] leading-none text-navy italic">
          {replay ? "Ready" : "Analyzing"}
        </span>
        <span className="text-[17px] text-mute">
          {replay
            ? run.replay === "guide"
              ? "바로 따라 하기 준비"
              : "다시 따라 하기 준비"
            : joined
              ? "진행 중인 분석에 합류했어요"
              : "영상 분석 중"}
        </span>
      </header>

      <div className="flex min-h-0 flex-1 flex-col justify-between gap-6 overflow-hidden px-10 pt-7 pb-8">
        <FlowSteps step={1} ready={replay} />

        <ScanPreview
          ytid={picked?.ytid ?? null}
          title={picked?.title ?? "분석 중인 영상"}
          status={
            fail
              ? `STOPPED · ${scanTime}`
              : done
                ? review
                  ? "IN REVIEW"
                  : "ANALYSIS COMPLETE"
                : `SCANNING · ${scanTime}`
          }
          running={running}
          pct={pct}
          rows={rows}
          foundCount={foundCount}
        />

        <AnalysisProgress
          pct={pct}
          phaseIdx={phaseIdx}
          phaseEn={phaseEn}
          phaseLabel={phaseLabel}
          eta={eta}
          failed={!!fail}
        />

        {notice ? (
          <div className="flex shrink-0 flex-col gap-3 rounded-3xl bg-cream px-7 py-6">
            <span className="font-label text-[15px] font-semibold tracking-[.14em] text-navy">
              {notice.tag}
            </span>
            <span className="font-display text-[28px] leading-[1.3] text-pretty text-ink">
              {notice.title}
            </span>
            <span className="text-[18px] leading-[1.5] text-pretty text-mute">{notice.sub}</span>
            {fail === "stopped" && retryError && (
              <span role="alert" className="text-[17px] leading-[1.5] text-pretty text-error">
                {retryError}
              </span>
            )}
          </div>
        ) : run.mode === "guide" && load.status === "ready" ? (
          <div className="rounded-3xl bg-cream px-7 py-6 text-[20px] text-ink">
            가이드 · {load.guide.steps.length}단계가 준비됐어요.
          </div>
        ) : (
          <FoundProducts
            rows={rows}
            foundCount={foundCount}
            haveCount={haveCount}
            onAdd={(row) =>
              setForm(
                emptyDraft({
                  cat: pouchCategory(row?.cat),
                  name: row?.name ?? "",
                  custom: Boolean(row?.name),
                }),
              )
            }
          />
        )}
      </div>

      <div className="flex shrink-0 flex-col gap-4 border-t border-line px-10 pt-5 pb-7">
        <ReadyStatus
          items={[
            ["가이드 준비", guideState, guideOk],
            [
              "얼굴 인식 준비",
              faceOk ? "완료" : faceCaptured ? "촬영 완료" : faceModal ? "등록 중" : "등록 필요",
              faceOk,
            ],
          ]}
        />
        {faceSaveError && (
          <p role="alert" className="text-[17px] text-error">
            {faceSaveError}
          </p>
        )}
        {jobId && !fail && !review && (
          <PillButton variant="line" size="hero" onClick={() => setPouchModal(true)}>
            내 파우치 확인 / 추가
          </PillButton>
        )}
        {fail ? (
          <div className="flex gap-3">
            {notice?.retry && (
              <PillButton
                size="hero"
                onClick={() => {
                  if (jobId) {
                    void retryJob();
                    return;
                  }
                  setDemoFail(null);
                  router.replace("/loading");
                }}
                disabled={retrying}
                className="flex-1"
              >
                {retrying ? "다시 시도하는 중" : "다시 시도"}
              </PillButton>
            )}
            <PillButton
              variant="line"
              size="hero"
              onClick={() => router.push("/select")}
              className="flex-1"
            >
              다른 영상 고르기
            </PillButton>
          </div>
        ) : (
          <PillButton
            size="hero"
            onClick={() => ctaGo?.()}
            disabled={(!approvedGuide && !review && !guideOk) || savingFace}
          >
            {ctaLabel}
          </PillButton>
        )}
      </div>

      {faceModal && (
        <FaceRegisterModal
          pct={pct}
          replay={replay}
          pouchReviewed={run.pouchReviewed}
          barText={barText}
          runId={run.id}
          onLater={() => {
            setFaceModal(false);
            setFaceShown(true);
            updateRun({ facePrompted: true }, run.id);
            if (!run.pouchReviewed) setPouchModal(true);
            camera.stop();
          }}
          onDone={async () => {
            let faceRegistrationId: string | null = null;
            const metadata =
              jobId && job
                ? faceRegistrationRequest(job.videoId, null)
                : run.mode === "guide" && load.status === "ready"
                  ? faceRegistrationRequest(load.guide.videoId, load.guide.guideId)
                  : null;
            if (jobId || run.mode === "guide") {
              const photo = facePhoto(run.id);
              if (!metadata || !photo) throw new Error("영상이나 얼굴 사진이 없다");
              faceRegistrationId = (await saveFace(photo, metadata)).faceRegistrationId;
              if (!isCurrentRun(run.id)) {
                await deleteFaceRegistration(faceRegistrationId).catch((e: unknown) =>
                  console.warn("얼굴 등록 정리 실패", e),
                );
                return;
              }
            }
            if (!isCurrentRun(run.id)) return;
            updateRun({ faceReg: true, facePrompted: true, faceRegistrationId }, run.id);
            setFaceShown(true);
            setFaceModal(false);
            if (!run.pouchReviewed) setPouchModal(true);
          }}
        />
      )}

      <PouchCheckModal
        open={pouchModal}
        pct={pct}
        barText={barText}
        pouch={state.pouch}
        changed={newIds.length > 0}
        onClose={closePouch}
        onEdit={(p) => setForm({ ...p })}
        onAdd={() => setForm(emptyDraft())}
      />

      {form && (
        <ProductSheet
          draft={form}
          onClose={() => setForm(null)}
          onSaved={(item, isNew) => isNew && setNewIds((ids) => [item.id, ...ids])}
        />
      )}
    </main>
  );
}
