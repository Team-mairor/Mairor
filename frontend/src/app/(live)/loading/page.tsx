"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { FlowSteps } from "@/components/flow-steps";
import { IconButton } from "@/components/ui/icon-button";
import { PillButton } from "@/components/ui/pill-button";
import { facePhoto, useCamera, useHiddenVideo } from "@/features/face";
import {
  AnalysisProgress,
  FaceRegisterModal,
  FoundProducts,
  jobReview,
  PouchCheckModal,
  ReadyStatus,
  ScanPreview,
  stageText,
  useAnalysisJob,
} from "@/features/loading";
import { emptyDraft, ProductSheet, type ProductDraft } from "@/features/pouch";
import { hasSame, useSession } from "@/features/session";
import { ANALYSIS_PHASES } from "@/features/video";
import { type AnalysisJobStatus, type ApiError } from "@/lib/api";
import { useQuery } from "@/lib/hooks/use-query";
import { REF_PRODUCTS, VIDEOS } from "@/mocks/mock-data";

const PHASE_EN = ["Queued", "Fetching", "Scenes", "Detecting", "Steps", "Composing"];

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
 * 04 로딩 · 준비 (VIDEO-003 · VIDEO-004). ?jobId=면 그 분석 작업 상태를 받고, 없으면 샘플로 움직인다.
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
  const { state, update, updateRun } = useSession();
  const camera = useCamera();
  const run = state.run;
  // 실제 작업에는 이전 실행의 '분석 없이 시작'이 섞이지 않게 한다
  const replay = !jobId && !!run.replay;
  const sample = !jobId;
  // 상태 응답에 영상 정보가 없어, 이 작업으로 시작한 실행의 영상만 쓰고 모르면 비워 둔다
  const picked = jobId ? (run.jobId === jobId ? run.picked : null) : (run.picked ?? VIDEOS[0]);
  // 사진은 메모리에만 있어서, 새로 고침으로 사라졌으면 다시 등록해야 한다
  const faceOk = run.faceReg && facePhoto(run.id) !== null;

  const [demoPct, setDemoPct] = useState(replay ? 100 : 0);
  const [joined, setJoined] = useState(false);
  const [demoFail, setDemoFail] = useState<Fail>(null);
  const [demoReview, setDemoReview] = useState<Review>(null);
  // 다시 따라 하기는 들어오자마자 등록부터 한다. 미리보기에서 돌아왔을 때처럼 이미 등록했으면 띄우지 않는다
  const [faceModal, setFaceModal] = useState(replay && !faceOk);
  const [faceShown, setFaceShown] = useState(replay);
  const [pouchModal, setPouchModal] = useState(false);
  const [newIds, setNewIds] = useState<string[]>([]);
  const [form, setForm] = useState<ProductDraft | null>(null);

  useEffect(() => {
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
  }, [query]);

  const live = useAnalysisJob(jobId);
  const job = jobId ? live.job : null;
  const pct = jobId ? live.pct : demoPct;
  const fail = jobId ? jobFail(live.error, job) : demoFail;
  const review: Review = job ? jobReview(job) : demoReview;

  useEffect(() => {
    if (live.error?.code === "UNAUTHORIZED") router.replace("/login?expired=basic");
  }, [live.error, router]);

  // 샘플 진행률 타이머
  const running = !replay && !fail && pct < 100;
  useEffect(() => {
    if (!running || !sample) return;
    const t = setInterval(() => setDemoPct((p) => Math.min(100, p + 1)), 600);
    return () => clearInterval(t);
  }, [running, sample]);

  // 4%가 되면 얼굴 등록 모달을 한 번 띄운다. 실패·검수 안내 중에는 띄우지 않는다
  useEffect(() => {
    if (pct >= 4 && !faceShown && !faceOk && !fail && !review) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- 진행률이 문턱을 넘는 순간 한 번만
      setFaceShown(true);
      setFaceModal(true);
    }
  }, [pct, faceShown, faceOk, fail, review]);

  // 등록 중이 아니면 추적을 쉬게 한다. 카메라는 켜 둬서 미리보기에서 바로 다시 돌린다
  // 등록 모달이 닫히면 프레임을 받는 곳이 없어 추적은 쉬고, 카메라는 미리보기에서 이어 쓴다.
  // 영상은 등록 모달의 원 안에만 보여 주므로 뒤에 깔린 전체 화면 영상은 숨긴다
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
          ? "검수 반려"
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

  // 실제 작업은 제품 인식이 연결되기 전까지 찾은 제품이 비어 있다
  const rows = (sample ? REF_PRODUCTS : []).map((r, i) => ({
    ...r,
    found: pct >= foundAt(i),
    next: pct < foundAt(i) && (i === 0 || pct >= foundAt(i - 1)),
    have: r.have || hasSame(r, state.pouch),
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
        // 다시 시도(API-VIDEO-006)는 BE 구현 전이라 다른 영상만 고를 수 있다
        stopped: {
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
            sub: "검수에서 반려됐어요. 다른 영상을 골라 주세요.",
            retry: false,
          }
        : null;

  const guideOk = replay || (done && !notice);
  const guideState = fail
    ? "멈춤"
    : review
      ? review === "pending"
        ? "검수 대기"
        : "이용 불가"
      : guideOk
        ? "완료"
        : `분석 중 ${pct}%`;

  let ctaLabel = "";
  let ctaGo: (() => void) | null = null;
  if (review === "pending") {
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
  else if (!faceOk) {
    ctaLabel = replay ? "얼굴 등록하고 입혀보기" : "얼굴 등록하고 미리보기";
    ctaGo = () => setFaceModal(true);
  } else {
    ctaLabel = replay ? "입혀보기" : "미리보기 보기";
    ctaGo = () => router.push("/preview");
  }

  const barText = replay
    ? run.replay === "guide"
      ? "검수된 가이드가 있어 분석 없이 시작해요"
      : "이전에 분석한 가이드를 그대로 써요"
    : "영상 분석은 그대로 진행 중이에요";

  const closePouch = () => {
    setPouchModal(false);
    if (replay) router.push("/preview");
  };

  return (
    <main className="relative flex min-h-dvh flex-1 flex-col bg-white text-ink">
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
          </div>
        ) : (
          <FoundProducts
            rows={rows}
            foundCount={foundCount}
            haveCount={haveCount}
            onAdd={() => setForm(emptyDraft({ brand: "", name: "" }))}
          />
        )}
      </div>

      <div className="flex shrink-0 flex-col gap-4 border-t border-line px-10 pt-5 pb-7">
        <ReadyStatus
          items={[
            ["가이드 준비", guideState, guideOk],
            ["얼굴 인식 준비", faceOk ? "완료" : faceModal ? "등록 중" : "등록 필요", faceOk],
          ]}
        />
        {fail ? (
          <div className="flex gap-3">
            {notice?.retry && (
              <PillButton
                size="hero"
                onClick={() => {
                  setDemoFail(null);
                  router.replace("/loading");
                }}
                className="flex-1"
              >
                다시 시도
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
          <PillButton size="hero" onClick={() => ctaGo?.()} disabled={!ctaGo}>
            {ctaLabel}
          </PillButton>
        )}
      </div>

      {faceModal && (
        <FaceRegisterModal
          pct={pct}
          replay={replay}
          barText={barText}
          runId={run.id}
          onLater={() => {
            setFaceModal(false);
            camera.stop();
          }}
          onDone={() => {
            updateRun({ faceReg: true });
            setFaceModal(false);
            if (pct < 100 || replay) setPouchModal(true);
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
