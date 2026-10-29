"use client";

import { X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Modal } from "@/components/ui/modal";
import { Spinner } from "@/components/ui/spinner";

export type GoogleResult = "ok" | "linked" | "fail" | "cancel";

/** 샘플 Google 계정. 두 번째는 같은 이메일의 자체 계정이 있는 경우 (USERS-004) */
const ACCOUNTS: {
  name: string;
  email: string;
  initial: string;
  bg: string;
  result: GoogleResult;
}[] = [
  {
    name: "김주연",
    email: "jooyeon.mairor@gmail.com",
    initial: "주",
    bg: "bg-pink-soft",
    result: "ok",
  },
  {
    name: "Jooyeon Kim",
    email: "hello.jooyeon@gmail.com",
    initial: "J",
    bg: "bg-sky",
    result: "linked",
  },
];

/**
 * Google 계정 선택 창을 흉내 낸다. 열려 있을 때만 그린다 (닫으면 언마운트).
 * ponytail: 실제 OAuth(API-USERS-006/007)가 붙으면 이 컴포넌트를 지우고 리다이렉트로 바꾼다.
 */
export function GoogleSheet({ onResult }: { onResult: (r: GoogleResult, email?: string) => void }) {
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => void (timer.current && clearTimeout(timer.current)), []);

  const pick = (a: (typeof ACCOUNTS)[number]) => {
    setBusy(true);
    timer.current = setTimeout(() => onResult(a.result, a.email), 900);
  };

  const cancel = () => {
    if (timer.current) clearTimeout(timer.current);
    onResult("cancel");
  };

  return (
    <Modal open onClose={cancel} labelledBy="google-sheet-title" className="flex flex-col gap-5">
      <div className="flex items-start gap-3.5">
        <span className="flex size-11 shrink-0 items-center justify-center rounded-full border border-line font-label text-[22px] font-bold text-ink">
          G
        </span>
        <div className="flex flex-1 flex-col gap-1">
          <h2 id="google-sheet-title" className="text-[20px] font-bold text-ink">
            계정 선택
          </h2>
          <span className="text-[16px] text-mute">mairor(으)로 이동할 Google 계정을 고르세요</span>
        </div>
        <button
          type="button"
          onClick={cancel}
          title="닫기"
          aria-label="닫기"
          className="flex size-11 shrink-0 items-center justify-center rounded-full text-ink hover:bg-cream"
        >
          <X className="size-5" strokeWidth={2} aria-hidden />
        </button>
      </div>
      {busy ? (
        <div className="flex h-[148px] flex-col items-center justify-center gap-3.5 text-[16px] text-mute">
          <Spinner tone="brand" className="size-7 border-[3px]" />
          Google 계정을 확인하고 있어요
        </div>
      ) : (
        <div className="flex flex-col overflow-hidden rounded-[18px] border border-line">
          {ACCOUNTS.map((a, i) => (
            <button
              key={a.email}
              type="button"
              onClick={() => pick(a)}
              className={`flex items-center gap-3.5 px-[18px] py-4 text-left hover:bg-cream-2 ${i ? "border-t border-line" : ""}`}
            >
              <span
                className={`flex size-10 items-center justify-center rounded-full text-[17px] font-bold text-ink ${a.bg}`}
              >
                {a.initial}
              </span>
              <span className="flex flex-col gap-0.5">
                <span className="text-[17px] font-semibold text-ink">{a.name}</span>
                <span className="text-[15px] text-mute">{a.email}</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </Modal>
  );
}
