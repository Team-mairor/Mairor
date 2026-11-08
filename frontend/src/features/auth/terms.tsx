"use client";

import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";

import { IconButton } from "@/components/ui/icon-button";
import { Modal } from "@/components/ui/modal";
import { PillButton } from "@/components/ui/pill-button";
import { AGREEMENT_VERSION } from "@/lib/validation";

export type TermsDoc = "TERMS" | "PRIVACY";

/** 약관 원문. 고치면 AGREEMENT_VERSION과 BE 약관 버전(AGREEMENT_*_VERSION)을 같이 올린다 */
const DOCS: Record<TermsDoc, { title: string; sections: { h: string; p: string[] }[] }> = {
  TERMS: {
    title: "서비스 이용약관",
    sections: [
      {
        h: "제1조 (목적)",
        p: [
          "이 약관은 Mairor(이하 '서비스')를 이용할 때 회원과 서비스 운영자 사이의 권리·의무와 책임을 정합니다.",
        ],
      },
      {
        h: "제2조 (정의)",
        p: [
          "'회원'은 이 약관에 동의하고 계정을 만든 사람입니다.",
          "'콘텐츠'는 회원이 서비스에 등록한 화장품 정보·사진·메이크업 리포트 등입니다.",
        ],
      },
      {
        h: "제3조 (약관의 효력과 변경)",
        p: [
          "이 약관은 가입 화면에 게시하고, 회원이 동의하면 효력이 생깁니다.",
          "약관을 바꿀 때는 시행일과 바뀌는 내용을 서비스 안에서 미리 알립니다.",
        ],
      },
      {
        h: "제4조 (회원가입)",
        p: [
          "만 14세 이상이면 이메일과 비밀번호 또는 Google 계정으로 가입할 수 있습니다.",
          "다른 사람의 정보로 가입하면 서비스 이용이 제한될 수 있습니다.",
        ],
      },
      {
        h: "제5조 (서비스 내용)",
        p: [
          "서비스는 메이크업 영상 분석과 단계별 가이드, 카메라를 이용한 메이크업 미리보기·따라하기, 보유 화장품(파우치) 관리와 매칭, 메이크업 리포트를 제공합니다.",
        ],
      },
      {
        h: "제6조 (회원의 의무)",
        p: [
          "회원은 자신의 계정 정보를 직접 관리하며, 다른 사람의 계정을 쓰거나 서비스 운영을 방해해서는 안 됩니다.",
          "다른 사람의 권리를 침해하는 콘텐츠를 등록해서는 안 됩니다.",
        ],
      },
      {
        h: "제7조 (이용 제한과 탈퇴)",
        p: [
          "회원은 언제든 탈퇴할 수 있습니다.",
          "회원이 제6조를 어기면 서비스 이용을 제한할 수 있습니다.",
        ],
      },
      {
        h: "제8조 (책임의 한계)",
        p: [
          "서비스가 보여 주는 가이드·미리보기·추천은 참고용이며 실제 화장 결과와 다를 수 있습니다.",
          "화장품 사용에 따른 피부 이상은 각 제품의 사용 안내를 따릅니다.",
          "분석에 쓰는 외부 영상의 권리는 원저작자에게 있습니다.",
        ],
      },
    ],
  },
  PRIVACY: {
    title: "개인정보 처리방침",
    sections: [
      {
        h: "개인정보 수집·이용 동의",
        p: [
          "가입 화면의 「개인정보 수집·이용 동의」는 아래 1~3항(수집 항목·목적·보유 기간)에 대한 동의입니다.",
          "동의를 거부할 수 있으며, 필수 항목에 동의하지 않으면 가입할 수 없습니다.",
        ],
      },
      {
        h: "1. 수집하는 항목",
        p: [
          "필수: 이메일, 비밀번호, 약관 동의 기록(종류·버전·동의 여부·동의 시각). Google로 가입하면 Google 계정 식별값과 이메일.",
          "선택: 닉네임, 이름, 휴대폰 번호, 생년월일, 성별.",
          "서비스 이용 중: 파우치에 등록한 화장품, 메이크업 리포트.",
          "메이크업을 따라 할 때: 얼굴 등록 이미지(정면 1장), 저장에 동의한 경우 단계별 얼굴 사진.",
        ],
      },
      {
        h: "2. 수집·이용 목적",
        p: [
          "회원 식별과 로그인, 가입 연령 확인, 메이크업 가이드·화장품 매칭·리포트 제공에 씁니다.",
          "얼굴 등록 이미지는 그 메이크업의 조명·색온도 기준으로만 쓰고, 단계별 얼굴 사진은 리포트의 과정 사진으로만 씁니다.",
          "선택 항목과 단계별 얼굴 사진은 동의하지 않아도 서비스를 이용할 수 있습니다.",
        ],
      },
      {
        h: "3. 보유·이용 기간",
        p: [
          "얼굴 등록 이미지와 단계별 얼굴 사진은 완료 리포트에 함께 보관하고, 리포트를 삭제하면 함께 삭제합니다.",
          "실시간 얼굴 인식에 쓰는 특징점은 얼굴 프로필로 저장하지 않습니다.",
          "그 밖의 정보는 탈퇴하면 지체 없이 파기합니다. 법령에 따라 보관해야 하는 정보는 그 기간 동안만 보관합니다.",
        ],
      },
      {
        h: "4. 제3자 제공",
        p: ["법령에 정해진 경우를 빼고는 회원의 동의 없이 개인정보를 다른 곳에 제공하지 않습니다."],
      },
      {
        h: "5. 회원의 권리",
        p: [
          "회원은 언제든 자신의 개인정보를 열람·정정·삭제하거나 처리 정지를 요구할 수 있고, 탈퇴로 동의를 철회할 수 있습니다.",
        ],
      },
      {
        h: "6. 안전성 확보 조치",
        p: [
          "비밀번호는 복원할 수 없는 방식(해시)으로 저장하고, 개인정보에 대한 접근을 제한합니다.",
        ],
      },
    ],
  },
};

const termsTitle = (doc: TermsDoc) => DOCS[doc].title;

/** 글이 짧아 스크롤할 게 없어도 끝까지 본 것으로 친다 */
const atEnd = (el: HTMLElement) => el.scrollTop + el.clientHeight >= el.scrollHeight - 8;

function TermsBody({ doc }: { doc: TermsDoc }) {
  return (
    <div className="flex flex-col gap-6 text-[16px] leading-relaxed text-ink">
      {DOCS[doc].sections.map((s) => (
        <section key={s.h} className="flex flex-col gap-2">
          <h3 className="text-[17px] font-bold">{s.h}</h3>
          {s.p.map((line) => (
            <p key={line}>{line}</p>
          ))}
        </section>
      ))}
      <p className="text-[15px] text-mute">시행일 {AGREEMENT_VERSION}</p>
    </div>
  );
}

/**
 * 가입 화면 위에 띄우는 원문 모달. 끝까지 스크롤해야 「확인」이 눌리고, 누르면 그 약관에 동의한다.
 * 화면을 떠나지 않아 입력값이 그대로 남는다.
 */
export function TermsModal({
  doc,
  onClose,
  onAgree,
}: {
  doc: TermsDoc;
  onClose: () => void;
  onAgree: () => void;
}) {
  const [read, setRead] = useState(false);
  // 창 크기가 바뀌어 남은 글이 다 보이게 돼도 다시 센다. observe 직후 한 번 불려 처음 판정도 겸한다
  const watchEnd = useCallback((el: HTMLDivElement) => {
    const ro = new ResizeObserver(() => {
      if (atEnd(el)) setRead(true);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return (
    <Modal
      open
      onClose={onClose}
      label={termsTitle(doc)}
      // 가입 화면이 스크롤돼 있어도 보이는 화면 가운데에 뜨게 fixed
      overlayClassName="fixed z-30 animate-fade"
      className="flex max-h-[80dvh] flex-col gap-5"
    >
      <div className="flex shrink-0 items-center justify-between">
        <h2 className="text-[22px] font-bold text-ink">{termsTitle(doc)}</h2>
        <IconButton icon="close" size={44} onClick={onClose} aria-label="닫기" />
      </div>
      <div
        ref={watchEnd}
        onScroll={(e) => atEnd(e.currentTarget) && setRead(true)}
        className="min-h-0 flex-1 overflow-y-auto"
      >
        <TermsBody doc={doc} />
      </div>
      <PillButton size="xl" className="w-full shrink-0" disabled={!read} onClick={onAgree}>
        {read ? "확인" : "끝까지 읽어 주세요"}
      </PillButton>
    </Modal>
  );
}

/** /terms · /privacy 정적 페이지 */
export function TermsPage({ doc }: { doc: TermsDoc }) {
  const router = useRouter();
  return (
    <main className="flex flex-1 flex-col bg-white">
      <header className="flex h-16 shrink-0 items-center gap-3.5 border-b border-line px-8">
        <IconButton
          size={44}
          // 주소로 바로 들어와 뒤로 갈 곳이 없으면 처음 화면으로
          onClick={() => (history.length > 1 ? router.back() : router.push("/"))}
          title="뒤로"
          aria-label="뒤로"
        />
        <h1 className="text-[20px] font-bold text-ink">{termsTitle(doc)}</h1>
      </header>
      <div className="flex-1 overflow-y-auto px-8 py-7">
        <TermsBody doc={doc} />
      </div>
    </main>
  );
}
