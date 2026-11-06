"use client";

import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { MirrorToggle } from "@/components/mirror-toggle";
import { saveFacePhoto } from "@/features/face";
import { useSession, type SessionState } from "@/features/session";
import { cn } from "@/lib/utils";
import { GUIDE_STEPS, VIDEOS } from "@/mocks/mock-data";

type Item = {
  label: string;
  sub: string;
  href: string;
  /** 이동 전에 맞춰 둘 세션 상태 */
  prep?: (s: SessionState) => Partial<SessionState>;
};

const ALL = GUIDE_STEPS.map((_, i) => i);
const loggedIn = { loggedIn: true, email: "hello@mairor.app" };
const run = (patch: Partial<SessionState["run"]>) => (s: SessionState) => ({
  ...loggedIn,
  run: { ...s.run, picked: s.run.picked ?? VIDEOS[0], ...patch },
});
/** 얼굴 등록을 마친 상태. 등록 완료는 사진이 있어야 인정하므로 빈 사진을 넣어 둔다 */
const faceRegistered = (s: SessionState) => {
  saveFacePhoto(s.run.id, new Blob());
  return run({ replay: null, faceReg: true })(s);
};

/** 프로토타입 왼쪽 '화면 바로가기' 목록. 개발 모드에서만 보인다 */
const ITEMS: Item[] = [
  { label: "인트로", sub: "로고 모션", href: "/" },
  { label: "로그인", sub: "이메일 · Google · 비밀번호 재설정", href: "/login" },
  { label: "회원가입", sub: "이메일 · 비밀번호 · 약관", href: "/signup" },
  { label: "온보딩", sub: "기능 소개 · 파우치 등록", href: "/onboarding", prep: () => loggedIn },
  {
    label: "홈",
    sub: "다시 따라 하기 · 파우치 · 리포트",
    href: "/home",
    prep: () => ({ ...loggedIn, pendingGuide: null }),
  },
  { label: "영상 입력", sub: "YouTube 검색 · Top 4", href: "/select", prep: () => loggedIn },
  {
    label: "로딩",
    sub: "분석 · 얼굴 등록 모달",
    href: "/loading",
    prep: run({ replay: null, faceReg: false }),
  },
  {
    label: "로딩 · 분석 실패",
    sub: "멈춘 단계 · 다시 시도",
    href: "/loading?fail=timeout",
    prep: faceRegistered,
  },
  {
    label: "로딩 · 검수 대기",
    sub: "분석 완료 ≠ 이용 가능",
    href: "/loading?review=pending",
    prep: faceRegistered,
  },
  { label: "미리보기", sub: "실시간 입혀보기 · 민낯 비교", href: "/preview", prep: run({}) },
  {
    label: "미리보기 · 인식 알림",
    sub: "이탈 · 회전 · 가림 · 거리 · 조명",
    href: "/preview?alert=lost",
    prep: run({}),
  },
  { label: "제품 체크", sub: "보유 · 대체 · 없음", href: "/check", prep: run({}) },
  {
    label: "제품 체크 · 빈 파우치",
    sub: "모두 없음 · 등록 안내",
    href: "/check?empty=1",
    prep: run({}),
  },
  { label: "입혀보며 고르기", sub: "부위별 실시간 대체", href: "/check?view=try", prep: run({}) },
  {
    label: "튜토리얼 안내",
    sub: "기능 소개 · 사진 저장 동의",
    href: "/tutorial/guide?force=1",
    prep: run({}),
  },
  {
    label: "튜토리얼",
    sub: "라이브 가이드 · 게이지 · 사진",
    href: "/tutorial",
    prep: run({ photoOk: true, captures: [] }),
  },
  {
    label: "튜토리얼 · 측정 불가",
    sub: "가림 · 이탈 시 게이지 멈춤",
    href: "/tutorial?alert=cover",
    prep: run({ photoOk: true }),
  },
  {
    label: "튜토리얼 · 사진 없이",
    sub: "동의 안 함 → 사진 없이 진행",
    href: "/tutorial?photo=0",
    prep: run({ photoOk: false, captures: [] }),
  },
  {
    label: "완성",
    sub: "기록 저장 · 최종 사진",
    href: "/done",
    prep: run({ photoOk: true, captures: ALL }),
  },
  {
    label: "완성 · 저장 실패",
    sub: "다시 시도 · 중복 저장 방지",
    href: "/done?fail=1",
    prep: run({ photoOk: true, captures: ALL }),
  },
  {
    label: "완성 · 사진 없음",
    sub: "미동의 → 미촬영 표시",
    href: "/done?photo=0",
    prep: run({ photoOk: false, captures: [] }),
  },
  { label: "내 파우치", sub: "제품 등록 · 수정 · 삭제", href: "/my/pouch", prep: () => loggedIn },
  {
    label: "내 파우치 · 비어 있음",
    sub: "빈 상태 · 제품 등록",
    href: "/my/pouch?empty=1",
    prep: () => loggedIn,
  },
  {
    label: "제품 등록 · 컬러 조회 실패",
    sub: "다시 시도 · 직접 입력",
    href: "/my/pouch?demo=shade-fail",
    prep: () => loggedIn,
  },
  { label: "리포트 목록", sub: "메이크업 기록", href: "/my/reports", prep: () => loggedIn },
  {
    label: "리포트 목록 · 비어 있음",
    sub: "빈 상태 · 영상 고르기",
    href: "/my/reports?empty=1",
    prep: () => loggedIn,
  },
  {
    label: "리포트 상세",
    sub: "스텝 사진 · 제품 비교 · 삭제",
    href: "/my/report",
    prep: () => loggedIn,
  },
  {
    label: "로그인 · 세션 만료",
    sub: "401 → 재로그인 안내",
    href: "/login?expired=basic",
    prep: () => ({ loggedIn: false }),
  },
  {
    label: "로그인 · 튜토리얼 중 만료",
    sub: "401 → 기록 없이 종료 안내",
    href: "/login?expired=tut",
    prep: () => ({ loggedIn: false }),
  },
  {
    label: "홈 · 첫 이용",
    sub: "리포트·파우치 빈 상태",
    href: "/home?empty=1",
    prep: () => loggedIn,
  },
  {
    label: "홈 · 검수 중 가이드",
    sub: "검수 대기 → 완료 후 시작",
    href: "/home",
    prep: () => ({
      ...loggedIn,
      pendingGuide: { title: VIDEOS[0].title, ytid: VIDEOS[0].ytid, status: "pending" },
    }),
  },
  {
    label: "영상 입력 · 조회 실패",
    sub: "검색·Top 4 불러오기 실패",
    href: "/select?fail=1",
    prep: () => loggedIn,
  },
  { label: "확인 · 얼굴 추적", sub: "랜드마크 · FPS · 색 측정", href: "/debug/face" },
  ...(process.env.GUIDE_EXPERIMENTS
    ? [
        {
          label: "확인 · 가이드 비교",
          sub: "블러셔 · 눈썹 변경 전/적용 후",
          href: "/debug/guide-compare",
        },
      ]
    : []),
  { label: "확인 · 레이어 합성", sub: "픽스처 얼굴 · 카메라 없이", href: "/debug/overlay" },
  { label: "확인 · 화장 레이어", sub: "카메라 · ?layers=경로", href: "/debug/preview" },
  { label: "확인 · 튜토리얼 가이드", sub: "카메라 · ?guides=경로", href: "/debug/tutorial" },
  { label: "확인 · 화면 크기", sub: "뷰포트 · DPR · 앱 축소 배율", href: "/debug/screen" },
];

/**
 * 개발용 화면 바로가기 패널. 프로토타입의 왼쪽 목록과 같다.
 */
export function DevNav() {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const { update, reset } = useSession();
  // 확인 화면은 화면 전체를 쓰므로 접힌 채로 시작한다
  const [open, setOpen] = useState(() => !pathname.startsWith("/debug"));

  const current = pathname + (search.size ? `?${search.toString()}` : "");
  const go = (item: Item) => {
    if (item.prep) update(item.prep);
    router.push(item.href);
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? "바로가기 닫기" : "바로가기 열기"}
        className="fixed bottom-4 left-4 z-[100] flex size-11 items-center justify-center rounded-full bg-ink text-white shadow-float"
      >
        {open ? (
          <PanelLeftClose className="size-5" aria-hidden />
        ) : (
          <PanelLeftOpen className="size-5" aria-hidden />
        )}
      </button>
      {open && (
        <nav
          aria-label="화면 바로가기"
          className="fixed top-4 bottom-[72px] left-4 z-[99] flex w-[212px] flex-col gap-1 overflow-y-auto rounded-[20px] bg-white px-3 py-[18px] text-ink shadow-float"
        >
          <div className="mb-2 flex flex-col gap-0.5 border-b border-line px-2.5 pb-3">
            <span className="font-serif text-[28px] leading-none text-navy italic">mairor</span>
            <span className="text-[13px] text-mute">v11 · 화면 바로가기</span>
          </div>
          {ITEMS.map((it, i) => {
            const on = current === it.href;
            return (
              <button
                key={it.href + it.label}
                type="button"
                onClick={() => go(it)}
                className={cn(
                  "flex min-h-11 shrink-0 items-center gap-2.5 rounded-xl px-2.5 py-2 text-left transition-colors",
                  on ? "bg-navy text-white" : "hover:bg-cream",
                )}
              >
                <span
                  className={cn(
                    "w-6 font-serif text-[18px] leading-none tabular",
                    on ? "text-blush" : "text-navy",
                  )}
                >
                  {String(i).padStart(2, "0")}
                </span>
                <span className="flex min-w-0 flex-col gap-px">
                  <span className="text-[14px] font-semibold">{it.label}</span>
                  <span className={cn("text-[12px]", on ? "text-blush" : "text-mute")}>
                    {it.sub}
                  </span>
                </span>
              </button>
            );
          })}
          <MirrorToggle className="mt-auto justify-between" />
          <button
            type="button"
            onClick={() => {
              reset();
              router.push("/");
            }}
            className="mt-1 flex min-h-11 shrink-0 items-center justify-center rounded-xl border border-line text-[16px] font-semibold"
          >
            처음부터 다시
          </button>
        </nav>
      )}
    </>
  );
}
