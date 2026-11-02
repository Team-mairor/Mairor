"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { MyHeader } from "@/features/my/my-header";
import { useSession } from "@/features/session";
import { useQuery } from "@/lib/use-query";

const PHOTO_POS = [
  { mt: "-62%", ml: "-40%", w: "180%" },
  { mt: "-112%", ml: "-55%", w: "210%" },
  { mt: "-150%", ml: "-60%", w: "220%" },
  { mt: "-86%", ml: "-70%", w: "240%" },
];
const ROT = [-1.6, 1.4, 1.2, -1.2];

/* eslint-disable @next/next/no-img-element -- 정적 내보내기 */

/** 마이페이지 · 리포트 목록 (REPORT-002) */
export default function MyReportsPage() {
  const { state } = useSession();
  const query = useQuery();
  const [top, ...rest] = query?.get("empty") === "1" ? [] : state.reports;

  return (
    <main className="relative flex min-h-0 flex-1 flex-col">
      <MyHeader tab="reports" />
      <div className="flex min-h-0 flex-1 flex-col gap-8 overflow-y-auto px-10 pt-1 pb-10">
        {!top ? (
          <div className="flex flex-col items-center gap-3.5 rounded-3xl border-[1.5px] border-dashed border-line-2 px-8 py-14 text-center">
            <span className="font-serif text-[34px] leading-none text-plum italic">
              No looks yet
            </span>
            <span className="font-display text-[26px] text-ink">아직 완료한 메이크업이 없어요</span>
            <span className="text-[18px] leading-[1.55] text-pretty text-mute">
              영상을 골라 끝까지 따라 하면 이곳에 리포트가 쌓여요.
            </span>
            <Link
              href="/select"
              className="mt-1.5 flex h-16 items-center rounded-full bg-pink px-7 text-[20px] font-bold text-white"
            >
              영상 고르러 가기
            </Link>
          </div>
        ) : (
          <>
            <Link
              href={`/my/report?id=${top.id}`}
              className="relative shrink-0 overflow-hidden rounded-[28px] bg-ink-deep transition-transform active:scale-[.99]"
            >
              <div className="relative h-[420px] overflow-hidden">
                {top.noPhoto || top.finalPhoto === false ? (
                  <div className="absolute inset-0 flex items-center justify-center bg-cream font-display text-[26px] text-ink">
                    미촬영
                  </div>
                ) : (
                  <img
                    src="/images/sample-face.png"
                    alt=""
                    className="absolute top-0 left-0 h-auto w-[140%] max-w-none"
                    style={{ marginTop: "-58%", marginLeft: "-20%" }}
                  />
                )}
                <span className="absolute top-5 left-5 flex h-9 items-center rounded-full bg-lime px-4 font-label text-[14px] font-bold tracking-[.12em] text-ink">
                  {top.isNew ? "NEW · 방금 완료" : "LATEST LOOK"}
                </span>
              </div>
              <div className="flex flex-col gap-4 px-7 pt-6 pb-[26px] text-white">
                <div className="flex items-end justify-between gap-4">
                  <div className="flex min-w-0 flex-col gap-1.5">
                    <span className="text-[16px] text-line-2">{top.date}</span>
                    <span className="font-display text-[34px] leading-[1.2]">{top.title}</span>
                  </div>
                  <span className="flex size-[60px] shrink-0 items-center justify-center rounded-full bg-white text-pink">
                    <ArrowRight className="size-[26px]" strokeWidth={2.4} aria-hidden />
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  {Array.from({ length: top.steps }, (_, i) => (
                    <span key={i} className="h-1.5 flex-1 rounded-full bg-pink" />
                  ))}
                </div>
                <span className="text-[16px] text-line-2">
                  {top.steps} / {top.steps} STEP 완료
                  {top.subs ? ` · 대체 제품 ${top.subs}개 사용` : " · 내 제품으로만"}
                </span>
              </div>
            </Link>

            <div className="flex flex-col gap-[18px]">
              <div className="flex items-baseline gap-2.5">
                <span className="font-serif text-[26px] leading-none text-ink italic">
                  Past looks
                </span>
                <span className="text-[16px] text-mute">지난 룩 · {rest.length}개</span>
              </div>
              <div className="grid grid-cols-2 gap-x-5 gap-y-7 px-1.5 pt-1">
                {rest.map((r, i) => (
                  <Link
                    key={r.id}
                    href={`/my/report?id=${r.id}`}
                    className="flex min-w-0 flex-col gap-3.5 rounded-[10px] bg-white px-3 pt-3 pb-[18px] shadow-[0_14px_30px_rgba(11,20,48,.12),0_0_0_1px_#E4E7EE] transition-transform hover:translate-y-[-4px] hover:rotate-0"
                    style={{ transform: `rotate(${ROT[i % 4]}deg)` }}
                  >
                    <div className="relative aspect-[4/5] overflow-hidden rounded bg-cream">
                      {r.noPhoto || r.finalPhoto === false ? (
                        <div className="absolute inset-0 flex items-center justify-center text-[16px] font-bold text-mute">
                          미촬영
                        </div>
                      ) : (
                        <img
                          src="/images/sample-face.png"
                          alt=""
                          className="absolute top-0 left-0 h-auto max-w-none"
                          style={
                            PHOTO_POS[i % 4] && {
                              marginTop: PHOTO_POS[i % 4].mt,
                              marginLeft: PHOTO_POS[i % 4].ml,
                              width: PHOTO_POS[i % 4].w,
                            }
                          }
                        />
                      )}
                    </div>
                    <div className="flex min-w-0 flex-col gap-1 px-1.5">
                      <span className="truncate font-display text-[22px] leading-[1.25] text-ink">
                        {r.title}
                      </span>
                      <span className="text-[15px] text-mute">
                        {r.date} · {r.steps} STEP
                      </span>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </main>
  );
}
