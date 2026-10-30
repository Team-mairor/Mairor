"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { IconButton } from "@/components/ui/icon-button";
import { Modal } from "@/components/ui/modal";
import { matchFor, useSession, type MatchResult, type ReportStep } from "@/features/session";
import { GUIDE_STEPS, REF_PRODUCTS } from "@/lib/mock-data";
import { useQuery } from "@/lib/use-query";

type DelState = null | "ask" | "busy" | "fail";

/* eslint-disable @next/next/no-img-element -- 정적 내보내기 */

const snapOf = (m: MatchResult): ReportStep => ({
  kind: m.kind,
  used: m.p ? { brand: m.p.brand, name: m.p.name } : null,
});

/** 리포트 상세 (REPORT-003 · REPORT-004). ?id=<리포트 id> */
export default function ReportPage() {
  const router = useRouter();
  const query = useQuery();
  const { state, hydrated, update } = useSession();
  const [expanded, setExpanded] = useState(true);
  const [del, setDel] = useState<DelState>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => void (timer.current && clearTimeout(timer.current)), []);

  // 정확한 id로만 찾는다. 저장값을 읽기 전에는 판단을 미룬다
  const id = query?.get("id");
  const rep = hydrated && id ? state.reports.find((r) => r.id === id) : undefined;
  const missing = hydrated && !!query && !rep;
  useEffect(() => {
    if (missing) router.replace("/my/reports");
  }, [missing, router]);

  // ponytail: 저장 당시 snapshot(items)이 있으면 그것을, 샘플 기록은 현재 파우치 기준 매칭을 쓴다.
  const steps = (rep ? GUIDE_STEPS.slice(0, rep.steps) : []).map((x, i) => {
    const snap = rep?.items?.[i];
    const m = snap ?? snapOf(matchFor(i, state.run, state.pouch));
    const used = m.used;
    const r = REF_PRODUCTS[i];
    return {
      no: i + 1,
      title: x.title,
      guide: x.guide,
      ref: `${r.brand} ${r.name}`,
      usedKind:
        m.kind === "same"
          ? "내가 쓴 제품 · 동일 제품"
          : m.kind === "sub"
            ? "내가 쓴 제품 · 대체"
            : "내가 쓴 제품",
      used: !used ? "없음 · 설명만" : `${used.brand} ${used.name}`,
      // 단계 사진: captures가 없는 샘플 기록은 전부 있음으로 본다
      noPhoto: !!rep?.noPhoto || (rep?.captures ? !rep.captures.includes(i) : false),
      bare: x.makeup === "foundation",
    };
  });
  // 최종 사진: 샘플 기록은 있음으로 본다
  const hasFinal = !!rep && !rep.noPhoto && (rep.finalPhoto ?? true);

  if (!rep) return null;

  const remove = () => {
    if (del === "busy") return;
    setDel("busy");
    timer.current = setTimeout(() => {
      update((prev) => ({ reports: prev.reports.filter((r) => r.id !== rep.id) }));
      router.replace("/my/reports");
    }, 700);
  };

  return (
    <main className="relative flex min-h-0 flex-1 flex-col">
      <header className="flex h-16 shrink-0 items-center gap-3.5 border-b border-line px-8">
        <IconButton
          size={44}
          onClick={() => router.push("/my/reports")}
          title="리포트 목록"
          aria-label="리포트 목록"
        />
        <span className="font-serif text-[28px] leading-none text-plum italic">Report</span>
        <span className="text-[17px] text-mute">메이크업 분석 리포트</span>
        <button
          type="button"
          onClick={() => setDel("ask")}
          className="ml-auto flex h-11 items-center rounded-full border-[1.5px] border-[#F0C9C5] px-[18px] text-[16px] font-bold text-error hover:bg-pink-pale"
        >
          삭제
        </button>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto px-10 pt-7 pb-8">
        <div className="flex flex-col gap-1.5">
          <span className="text-[16px] text-mute">
            {rep.date} · {rep.steps}단계
          </span>
          <h1 className="font-display text-[34px] leading-[1.25] text-ink">{rep.title}</h1>
        </div>

        <div className="relative h-[480px] shrink-0 overflow-hidden rounded-3xl border border-line">
          {!hasFinal ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2.5 bg-cream">
              <span className="font-display text-[26px] text-ink">미촬영</span>
              <span className="text-[17px] text-mute">
                {rep.noPhoto ? "사진 없이 완료한 메이크업이에요" : "마지막 단계 사진이 없어요"}
              </span>
            </div>
          ) : (
            <img
              src="/images/sample-face.png"
              alt="완성 사진"
              className="absolute top-0 left-0 h-auto w-[187.9%] max-w-none"
              style={{ marginTop: "-104.8%" }}
            />
          )}
          <span className="absolute top-[18px] left-[18px] rounded-full bg-white px-[18px] py-2.5 font-label text-[15px] font-semibold tracking-[.14em] text-ink">
            FINAL LOOK
          </span>
        </div>

        <section className="flex flex-col gap-3.5">
          <div className="flex items-baseline justify-between gap-3">
            <span className="flex items-baseline gap-2.5">
              <span className="font-serif text-[26px] leading-none text-ink italic">
                Step captures
              </span>
              <span className="text-[16px] text-mute">스텝별 내 얼굴</span>
            </span>
            <button
              type="button"
              onClick={() => setExpanded((e) => !e)}
              className="text-[17px] font-semibold text-plum"
              aria-expanded={expanded}
            >
              {expanded ? "접기" : "펼쳐보기"}
            </button>
          </div>
          {expanded && (
            <div className="grid grid-cols-4 gap-2.5">
              {steps.map((c) => (
                <div key={c.no} className="flex flex-col gap-1.5">
                  <div className="relative aspect-square overflow-hidden rounded-[14px] border border-line">
                    {c.noPhoto ? (
                      <div className="absolute inset-0 z-[1] flex items-center justify-center bg-cream text-[16px] font-bold text-mute">
                        미촬영
                      </div>
                    ) : c.bare ? (
                      <img
                        src="/images/sample-face-bare.png"
                        alt=""
                        className="absolute top-0 h-auto w-[193.9%] max-w-none"
                        style={{ left: "-73.6%", marginTop: "-72.7%" }}
                      />
                    ) : (
                      <img
                        src="/images/sample-face.png"
                        alt=""
                        className="absolute top-0 left-0 h-auto w-[187.9%] max-w-none"
                        style={{ marginTop: "-86.7%" }}
                      />
                    )}
                    <span className="absolute top-2 left-2 rounded-full bg-white px-2 py-[3px] font-serif text-[18px] text-ink">
                      {c.no}
                    </span>
                  </div>
                  <span className="text-[16px] text-ink">{c.title}</span>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="flex flex-col">
          <div className="flex items-baseline gap-2.5 pb-3">
            <span className="font-serif text-[26px] leading-none text-ink italic">Step guide</span>
            <span className="text-[16px] text-mute">순서 · 레퍼런스 제품 / 내가 쓴 제품</span>
          </div>
          {steps.map((c) => (
            <div
              key={c.no}
              className="grid grid-cols-[40px_minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1fr)] items-start gap-3.5 border-t border-line py-3.5"
            >
              <span className="font-serif text-[26px] leading-none text-plum">{c.no}</span>
              <span className="flex flex-col gap-1">
                <span className="font-display text-[17px] text-ink">{c.title}</span>
                <span className="text-[16px] leading-[1.45] text-mute">{c.guide}</span>
              </span>
              <span className="flex flex-col gap-[3px] text-[16px]">
                <span className="text-mute">레퍼런스</span>
                <span className="font-semibold text-ink">{c.ref}</span>
              </span>
              <span className="flex flex-col gap-[3px] text-[16px]">
                <span className="text-mute">{c.usedKind}</span>
                <span className="font-semibold text-ink">{c.used}</span>
              </span>
            </div>
          ))}
        </section>
      </div>

      <Modal
        open={!!del}
        onClose={() => del !== "busy" && setDel(null)}
        className="flex max-w-[540px] flex-col gap-[22px] px-[30px] pt-[34px] pb-[26px]"
      >
        <div className="flex flex-col gap-2.5">
          <h2 className="font-display text-[30px] leading-[1.25] text-ink">
            {del === "fail"
              ? "삭제하지 못했어요"
              : del === "busy"
                ? "삭제 중…"
                : "이 리포트를 삭제할까요?"}
          </h2>
          <p className="text-[18px] leading-[1.55] text-mute">
            {del === "fail"
              ? "잠시 후 다시 시도해 주세요."
              : "단계 사진도 함께 삭제돼요. 삭제한 리포트는 되돌릴 수 없어요."}
          </p>
        </div>
        <div className="flex gap-2.5">
          <button
            type="button"
            onClick={() => setDel(null)}
            disabled={del === "busy"}
            className="flex h-[68px] flex-1 items-center justify-center rounded-full border-[1.5px] border-line-2 text-[19px] font-bold text-ink disabled:opacity-50"
          >
            취소
          </button>
          <button
            type="button"
            onClick={remove}
            disabled={del === "busy"}
            className="flex h-[68px] flex-1 items-center justify-center rounded-full bg-error text-[19px] font-bold text-white disabled:opacity-70"
          >
            {del === "fail" ? "다시 시도" : "삭제"}
          </button>
        </div>
      </Modal>
    </main>
  );
}
