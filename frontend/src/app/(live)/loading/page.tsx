"use client";

import { Plus, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { FlowSteps } from "@/components/flow-steps";
import { IconButton } from "@/components/ui/icon-button";
import { useCamera, useHiddenVideo } from "@/features/face";
import { facePhoto } from "@/features/loading/face-register";
import { FaceRegisterModal, ProgressBar } from "@/features/loading/face-register-modal";
import { emptyDraft, PouchBoard, ProductSheet, type ProductDraft } from "@/features/pouch";
import { hasSame, useSession } from "@/features/session";
import { ANALYSIS_PHASES, REF_PRODUCTS, VIDEOS, videoThumb } from "@/lib/mock-data";
import { useQuery } from "@/lib/use-query";
import { cn } from "@/lib/utils";

const PHASE_EN = ["Queued", "Fetching", "Scenes", "Detecting", "Steps", "Composing"];
const TAG_POS: [number, number][] = [
  [50, 60],
  [34, 45],
  [30, 28],
  [66, 28],
  [20, 62],
  [66, 50],
  [50, 80],
];

/** i번째 제품을 찾았다고 보여 줄 진행률. 단계 수와 상관없이 6~90% 사이에 고르게 나눈다 */
const foundAt = (i: number) => 6 + (i * 84) / REF_PRODUCTS.length;

type Fail = null | "timeout" | "failed";
type Review = null | "pending" | "rejected";

/**
 * 04 로딩 · 준비 (VIDEO-003 · VIDEO-004). 분석 진행 + 얼굴 등록 모달 + 파우치 확인 모달.
 * ?joined=1 진행 중 분석 합류 · ?fail=timeout|failed · ?review=pending|rejected 는 상태 확인용.
 * ponytail: 진행률은 타이머(0.6초에 1%). 분석 상태 조회 API가 붙으면 pct·progressStage를 응답으로 바꾼다.
 */
export default function LoadingPage() {
  const router = useRouter();
  const query = useQuery();
  const { state, update, updateRun } = useSession();
  const camera = useCamera();
  const run = state.run;
  const replay = !!run.replay;
  const picked = run.picked ?? VIDEOS[0];
  // 사진은 메모리에만 있어서, 새로 고침으로 사라졌으면 다시 등록해야 한다
  const faceOk = run.faceReg && facePhoto(run.id) !== null;

  const [pct, setPct] = useState(replay ? 100 : 0);
  const [joined, setJoined] = useState(false);
  const [fail, setFail] = useState<Fail>(null);
  const [review, setReview] = useState<Review>(null);
  // 다시 따라 하기는 들어오자마자 등록부터 한다. 미리보기에서 돌아왔을 때처럼 이미 등록했으면 띄우지 않는다
  const [faceModal, setFaceModal] = useState(replay && !faceOk);
  const [faceShown, setFaceShown] = useState(replay);
  const [pouchModal, setPouchModal] = useState(false);
  const [newIds, setNewIds] = useState<string[]>([]);
  const [form, setForm] = useState<ProductDraft | null>(null);

  useEffect(() => {
    if (!query) return;
    if (query.get("joined")) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- 주소로 받은 상태를 한 번 반영한다
      setJoined(true);
      setPct(46);
    }
    const f = query.get("fail");
    if (f === "timeout" || f === "failed") {
      setFail(f);
      setPct(38);
      setFaceShown(true);
    }
    const r = query.get("review");
    if (r === "pending" || r === "rejected") {
      setReview(r);
      setPct(100);
      setFaceShown(true);
    }
  }, [query]);

  // 진행률 타이머
  const running = !replay && !fail && pct < 100;
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setPct((p) => Math.min(100, p + 1)), 600);
    return () => clearInterval(t);
  }, [running]);

  // 4%가 되면 얼굴 등록 모달을 한 번 띄운다
  useEffect(() => {
    if (pct >= 4 && !faceShown && !faceOk) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- 진행률이 문턱을 넘는 순간 한 번만
      setFaceShown(true);
      setFaceModal(true);
    }
  }, [pct, faceShown, faceOk]);

  // 등록 중이 아니면 추적을 쉬게 한다. 카메라는 켜 둬서 미리보기에서 바로 다시 돌린다
  // 등록 모달이 닫히면 프레임을 받는 곳이 없어 추적은 쉬고, 카메라는 미리보기에서 이어 쓴다.
  // 영상은 등록 모달의 원 안에만 보여 주므로 뒤에 깔린 전체 화면 영상은 숨긴다
  useHiddenVideo();

  const done = pct >= 100;
  const phaseIdx = done ? 6 : ANALYSIS_PHASES.filter((p) => pct >= p[2]).length - 1;
  const pi = Math.max(0, Math.min(5, phaseIdx));
  const phaseName = ANALYSIS_PHASES[pi][1];
  const phaseLabel = fail
    ? `${phaseName} 단계에서 멈췄어요`
    : done
      ? review === "pending"
        ? "분석 완료 · 검수 대기"
        : review === "rejected"
          ? "검수 반려"
          : "분석이 끝났어요"
      : `${phaseName} 중…`;
  const phaseEn = fail ? "Stopped." : done ? (review ? "In review." : "Ready.") : PHASE_EN[pi];
  const eta = fail ? "멈춤" : done ? "완료" : `약 ${Math.ceil((100 - pct) * 0.6)}초 남음`;
  const scanSec = Math.floor(pct * 7.5);
  const scanTime = `${Math.floor(scanSec / 60)}:${String(scanSec % 60).padStart(2, "0")}`;

  const rows = REF_PRODUCTS.map((r, i) => ({
    ...r,
    found: pct >= foundAt(i),
    next: pct < foundAt(i) && (i === 0 || pct >= foundAt(i - 1)),
    have: r.have || hasSame(r, state.pouch),
  }));
  const foundCount = rows.filter((r) => r.found).length;
  const haveCount = rows.filter((r) => r.have).length;

  const notice = fail
    ? fail === "timeout"
      ? {
          tag: "STOPPED · TIMEOUT",
          title: "분석이 너무 오래 걸려 멈췄어요",
          sub: `${phaseName} 단계에서 멈췄어요. 다시 시도하면 이 단계부터 이어서 분석해요.`,
          retry: true,
        }
      : {
          tag: "STOPPED · FAILED",
          title: "이 영상은 분석할 수 없어요",
          sub: `${phaseName} 단계에서 메이크업 장면을 찾지 못했어요. 다른 영상을 골라 주세요.`,
          retry: false,
        }
    : review === "pending"
      ? {
          tag: "IN REVIEW",
          title: "분석은 끝났고, 검수 중이에요",
          sub: "검수를 통과한 가이드만 따라 할 수 있어요. 검수가 끝나면 홈에서 바로 시작할 수 있어요.",
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
      update({ pendingGuide: { title: picked.title, ytid: picked.ytid, status: "pending" } });
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
        <span className="font-serif text-[28px] leading-none text-plum italic">
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

        {/* 영상 썸네일 위 스캔 연출. 사진 위라 미러필름 모드에서도 흰 선·점은 흰색 그대로 둔다(data-dark) */}
        <div
          data-dark
          className="relative aspect-video w-full shrink-0 overflow-hidden rounded-3xl bg-ink"
        >
          <div
            className="absolute inset-0 bg-cover bg-center"
            style={{ backgroundImage: `url(${videoThumb(picked.ytid)})` }}
          />
          <div className="absolute inset-0 bg-[rgba(11,20,48,.18)]" />
          <div className="absolute inset-7">
            <span className="absolute top-0 left-0 size-[34px] rounded-tl-[10px] border-t-2 border-l-2 border-white" />
            <span className="absolute top-0 right-0 size-[34px] rounded-tr-[10px] border-t-2 border-r-2 border-white" />
            <span className="absolute bottom-0 left-0 size-[34px] rounded-bl-[10px] border-b-2 border-l-2 border-white" />
            <span className="absolute right-0 bottom-0 size-[34px] rounded-br-[10px] border-r-2 border-b-2 border-white" />
          </div>
          {running && (
            <div
              data-dark
              className="absolute inset-x-7 h-[1.5px] bg-white shadow-[0_0_16px_3px_rgba(255,255,255,.55)]"
              style={{ top: `${10 + ((pct * 9) % 100) * 0.8}%` }}
            />
          )}
          {/* 자리가 TAG_POS만큼이라, 단계가 많으면 가장 최근에 찾은 것만 남겨 겹치지 않게 한다 */}
          {rows.map((r, i) =>
            r.found && i >= foundCount - TAG_POS.length ? (
              <div
                key={r.id}
                className="absolute flex items-center gap-2"
                style={{
                  left: `${TAG_POS[i % TAG_POS.length][0]}%`,
                  top: `${TAG_POS[i % TAG_POS.length][1]}%`,
                  animation: "mr-fade 600ms cubic-bezier(.34,1.56,.64,1) both",
                }}
              >
                <span
                  data-dark
                  className="size-2.5 rounded-full bg-white"
                  style={{ animation: "mr-pulse 1.6s ease-out infinite" }}
                />
                <span className="rounded-full bg-white/90 px-2.5 py-1 text-[12px] font-semibold whitespace-nowrap text-ink">
                  {r.cat}
                </span>
              </div>
            ) : null,
          )}
          <span className="absolute bottom-[18px] left-5 rounded-full bg-white px-3 py-[7px] font-label text-[11px] font-semibold tracking-[.14em] text-ink">
            {fail
              ? `STOPPED · ${scanTime}`
              : done
                ? review
                  ? "IN REVIEW"
                  : "ANALYSIS COMPLETE"
                : `SCANNING · ${scanTime}`}
          </span>
          <span className="absolute right-5 bottom-[18px] max-w-[55%] truncate text-[13px] font-semibold text-white">
            {picked.title}
          </span>
        </div>

        <div className="flex shrink-0 flex-col gap-3.5">
          <div className="flex items-end justify-between gap-5">
            <span className="font-serif text-[120px] leading-[.8] tracking-[-.03em] text-ink tabular">
              {pct}
              <span className="text-[44px] text-plum">%</span>
            </span>
            <span className="flex flex-col items-end gap-1.5 pb-1">
              <span className="font-serif text-[32px] leading-none text-plum italic">
                {phaseEn}
              </span>
              <span className="text-[17px] whitespace-nowrap text-mute">
                {phaseLabel} · {eta}
              </span>
            </span>
          </div>
          <div className="relative h-0.5 bg-line">
            <div
              className="absolute top-0 left-0 h-0.5 bg-ink transition-[width] duration-600 ease-linear"
              style={{ width: `${pct}%` }}
            />
            <div
              className="absolute -top-1 -ml-[5px] size-2.5 rounded-full bg-pink-deep transition-[left] duration-600 ease-linear"
              style={{ left: `${pct}%` }}
            />
          </div>
          <div className="grid grid-cols-6 gap-2">
            {ANALYSIS_PHASES.map(([en], i) => (
              <span
                key={en}
                className={cn(
                  "font-label text-[15px] font-semibold tracking-[.12em] transition-colors",
                  fail && i === phaseIdx ? "text-error" : i <= phaseIdx ? "text-ink" : "text-mute",
                )}
              >
                {en}
              </span>
            ))}
          </div>
        </div>

        {notice ? (
          <div className="flex shrink-0 flex-col gap-3 rounded-3xl bg-cream px-7 py-6">
            <span className="font-label text-[15px] font-semibold tracking-[.14em] text-plum">
              {notice.tag}
            </span>
            <span className="font-display text-[28px] leading-[1.3] text-pretty text-ink">
              {notice.title}
            </span>
            <span className="text-[18px] leading-[1.5] text-pretty text-mute">{notice.sub}</span>
          </div>
        ) : (
          <div className="flex shrink-0 flex-col gap-3">
            <div className="flex items-baseline justify-between gap-3">
              <span className="flex min-w-0 items-baseline gap-2.5">
                <span className="font-serif text-[32px] leading-none whitespace-nowrap text-ink italic">
                  Found in video
                </span>
                <span className="truncate text-[19px] text-mute">
                  없는 제품은 탭해서 파우치에 추가
                </span>
              </span>
              <span className="text-[19px] whitespace-nowrap text-mute tabular">
                {foundCount} / {REF_PRODUCTS.length} · 파우치 {haveCount}
              </span>
            </div>
            {/* 단계 수는 영상마다 달라, 두 줄을 넘으면 이 안에서 넘겨 본다 */}
            <div className="grid max-h-[168px] grid-cols-4 gap-2 overflow-y-auto">
              {rows.map((r) =>
                r.found ? (
                  <button
                    key={r.id}
                    type="button"
                    disabled={r.have}
                    onClick={() => setForm(emptyDraft({ brand: "", name: "" }))}
                    className={cn(
                      "flex h-20 items-center gap-3 rounded-[20px] border px-4 text-left transition-colors",
                      r.have ? "border-plum bg-plum" : "border-line bg-white",
                    )}
                    style={{ animation: "mr-fade 600ms cubic-bezier(.34,1.56,.64,1) both" }}
                  >
                    <span
                      className="size-[34px] shrink-0 rounded-full border-2 border-white shadow-[0_0_0_1px_#E4E7EE]"
                      style={{ background: r.color }}
                    />
                    <span className="flex min-w-0 flex-col gap-0.5 overflow-hidden">
                      <span
                        className={cn(
                          "truncate text-[21px] font-semibold",
                          r.have ? "text-white" : "text-mute",
                        )}
                      >
                        {r.cat}
                      </span>
                      <span
                        className={cn(
                          "truncate text-[18px]",
                          r.have ? "text-pink-soft" : "text-mute",
                        )}
                      >
                        {r.have ? "보유" : "없음 · 추가"}
                      </span>
                    </span>
                  </button>
                ) : (
                  <div
                    key={r.id}
                    className="flex h-20 items-center gap-3 rounded-[20px] border border-dashed border-line-3 px-4 text-[19px] text-mute"
                  >
                    <span className="size-[34px] shrink-0 rounded-full bg-cream" />
                    {r.next ? "찾는 중…" : "대기"}
                  </div>
                ),
              )}
            </div>
          </div>
        )}
      </div>

      <div className="flex shrink-0 flex-col gap-4 border-t border-line px-10 pt-5 pb-7">
        <div className="grid grid-cols-2 gap-3">
          {(
            [
              ["가이드 준비", guideState, guideOk],
              ["얼굴 인식 준비", faceOk ? "완료" : faceModal ? "등록 중" : "등록 필요", faceOk],
            ] as [string, string, boolean][]
          ).map(([label, st, ok]) => (
            <div
              key={label}
              className="flex h-[68px] min-w-0 items-center gap-3 rounded-[20px] border border-line px-5"
            >
              <span
                className={cn("size-3 shrink-0 rounded-full", ok ? "bg-pink-deep" : "bg-line-3")}
              />
              <span className="text-[21px] font-semibold whitespace-nowrap text-ink">{label}</span>
              <span
                className={cn(
                  "ml-auto text-[20px] font-semibold whitespace-nowrap tabular",
                  ok ? "text-plum" : "text-mute",
                )}
              >
                {st}
              </span>
            </div>
          ))}
        </div>
        {fail ? (
          <div className="flex gap-3">
            {notice?.retry && (
              <button
                type="button"
                onClick={() => {
                  setFail(null);
                  router.replace("/loading");
                }}
                className="flex h-20 flex-1 items-center justify-center rounded-full bg-pink text-[23px] font-bold text-white active:scale-[.98]"
              >
                다시 시도
              </button>
            )}
            <button
              type="button"
              onClick={() => router.push("/select")}
              className="flex h-20 flex-1 items-center justify-center rounded-full border-[1.5px] border-ink text-[23px] font-bold text-ink active:scale-[.98]"
            >
              다른 영상 고르기
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => ctaGo?.()}
            disabled={!ctaGo}
            className={cn(
              "flex h-20 items-center justify-center rounded-full px-6 text-center text-[23px] font-bold transition-colors active:scale-[.98] disabled:cursor-default",
              ctaGo ? "bg-pink text-white" : "bg-line text-mute",
            )}
          >
            {ctaLabel}
          </button>
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

      {pouchModal && (
        <div
          className="absolute inset-0 z-[4] flex items-center justify-center bg-[rgba(8,13,34,.62)] p-8"
          role="dialog"
          aria-modal="true"
          aria-label="내 파우치 확인"
        >
          <div className="flex w-full flex-col overflow-hidden rounded-[32px] bg-white shadow-[0_30px_80px_rgba(8,13,34,.35)]">
            <ProgressBar pct={pct} text={barText} />
            <div className="flex animate-step-in flex-col gap-[22px] px-8 pt-7 pb-8">
              <div className="flex w-full items-center justify-between gap-3">
                <span className="flex items-center gap-2.5 text-[16px] font-bold text-plum">
                  <span className="flex gap-1.5">
                    <span className="h-1.5 w-[22px] rounded-full bg-pink-soft" />
                    <span className="h-1.5 w-[22px] rounded-full bg-pink-deep" />
                  </span>
                  STEP 2 · 내 파우치
                </span>
                <button
                  type="button"
                  onClick={closePouch}
                  className="ml-auto flex h-14 items-center gap-3 text-[24px] font-bold whitespace-nowrap text-ink"
                >
                  {newIds.length ? "다 했어요" : "변경 없어요"}
                  <span className="flex size-11 items-center justify-center rounded-full bg-ink text-white">
                    <X className="size-5" strokeWidth={3} aria-hidden />
                  </span>
                </button>
              </div>
              <div className="flex flex-col gap-2">
                <span className="font-display text-[30px] leading-[1.3] text-ink">
                  기다리는 동안
                  <br />내 파우치를 확인해 볼까요?
                </span>
                <span className="text-[19px] leading-[1.5] text-mute">
                  최근에 산 제품이 있다면 지금 등록해 두세요. 분석 결과에 바로 반영돼요.
                </span>
              </div>
              <PouchBoard
                items={state.pouch}
                scale={0.6}
                className="h-[440px] shrink-0"
                onEdit={(p) => setForm({ ...p })}
              >
                <div className="absolute top-5 left-[22px] z-[6]">
                  <span className="flex flex-col gap-1 rounded-[14px] bg-white px-[18px] py-3">
                    <span className="font-serif text-[32px] leading-none text-ink italic">
                      My pouch
                    </span>
                    <span className="text-[16px] text-mute">
                      {state.pouch.length}개 · 탭해서 수정
                    </span>
                  </span>
                </div>
              </PouchBoard>
              <button
                type="button"
                onClick={() => setForm(emptyDraft())}
                className="flex h-20 items-center justify-center gap-2.5 rounded-full bg-pink text-[22px] font-bold text-white shadow-[0_14px_30px_color-mix(in_srgb,var(--color-pink)_26%,transparent)] active:scale-[.97]"
              >
                <Plus className="size-[22px]" strokeWidth={2.6} aria-hidden />새 제품 등록하기
              </button>
            </div>
          </div>
        </div>
      )}

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
