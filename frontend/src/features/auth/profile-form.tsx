"use client";

import { Check } from "lucide-react";
import { useState, useSyncExternalStore } from "react";

import { FieldError } from "@/components/ui/notice";
import { TextField } from "@/components/ui/text-field";
import { ApiError, type SignUpRequest, type SignupAgreement } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  AGREEMENT_VERSION,
  profileProblem,
  profileValue,
  type ProfileField,
} from "@/lib/validation";

import { TermsModal, type TermsDoc } from "./terms";

const AGREEMENTS = [
  { type: "TERMS", label: "[필수] 서비스 이용약관", required: true, doc: "TERMS" },
  { type: "PRIVACY", label: "[필수] 개인정보 수집·이용 동의", required: true, doc: "PRIVACY" },
  { type: "AGE_OVER_14", label: "[필수] 만 14세 이상입니다", required: true, doc: null },
  { type: "MARKETING", label: "[선택] 마케팅 정보 수신 동의", required: false, doc: null },
] as const;
type AgreeType = (typeof AGREEMENTS)[number]["type"];
const agreeAll = (on: boolean) =>
  Object.fromEntries(AGREEMENTS.map((a) => [a.type, on])) as Record<AgreeType, boolean>;

/** 선택 항목 중 글자로 받는 칸 */
const PROFILE_INPUTS = [
  {
    field: "nickname",
    label: "닉네임",
    placeholder: "2~20자, 한글·영문·숫자·밑줄",
    autoComplete: "nickname",
    inputMode: "text",
    maxLength: 20,
  },
  {
    field: "name",
    label: "이름",
    placeholder: "2~50자, 한글·영문",
    autoComplete: "name",
    inputMode: "text",
    maxLength: 50,
  },
  {
    field: "phone",
    label: "휴대폰 번호",
    placeholder: "010-1234-5678",
    autoComplete: "tel",
    inputMode: "tel",
    maxLength: 13,
  },
] as const;
type Profile = Record<ProfileField | "birthDate", string>;
const EMPTY_PROFILE: Profile = { nickname: "", name: "", phone: "", birthDate: "" };

type Gender = NonNullable<SignUpRequest["gender"]>;
const GENDERS: { value: Gender; label: string }[] = [
  { value: "FEMALE", label: "여성" },
  { value: "MALE", label: "남성" },
];

/** 서버 입력 오류를 칸 아래에 보여 줄 선택 항목 */
export const EXTRA_FIELDS = ["nickname", "name", "phone", "birthDate", "gender"] as const;
type ExtraField = (typeof EXTRA_FIELDS)[number];

/** 가입 요청에 싣는 추가 정보와 약관 동의 */
type ProfilePayload = Pick<
  SignUpRequest,
  "nickname" | "name" | "phone" | "birthDate" | "gender"
> & { agreements: SignupAgreement[] };

/** 오늘(기기 시간대) YYYY-MM-DD. 생년월일 상한 */
const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const noSubscribe = () => () => {};

export function useProfileForm(initial: Partial<Profile> = {}) {
  const [profile, setProfile] = useState<Profile>({ ...EMPTY_PROFILE, ...initial });
  const [gender, setGender] = useState<Gender | null>(null);
  const [agree, setAgree] = useState(() => agreeAll(false));
  const [extraErr, setExtraErr] = useState<Partial<Record<ExtraField, string>>>({});
  const [agreeErr, setAgreeErr] = useState<string | null>(null);

  const requiredAgreed = AGREEMENTS.every((a) => !a.required || agree[a.type]);
  const profileOk = PROFILE_INPUTS.every((p) => !profileProblem(p.field, profile[p.field]));

  const payload = (): ProfilePayload => ({
    nickname: profileValue("nickname", profile.nickname),
    name: profileValue("name", profile.name),
    phone: profileValue("phone", profile.phone),
    birthDate: profile.birthDate || undefined,
    gender: gender ?? undefined,
    agreements: AGREEMENTS.map((a) => ({
      type: a.type,
      version: AGREEMENT_VERSION,
      agreed: agree[a.type],
    })),
  });

  const clearErrors = () => {
    setExtraErr({});
    setAgreeErr(null);
  };

  /** 추가 정보·약관 칸의 서버 오류를 칸 아래에 표시한다. 이 칸들 밖의 오류가 남으면 false */
  const applyError = (e: unknown) => {
    if (!(e instanceof ApiError)) return false;
    if (e.code === "USERS_REQUIRED_AGREEMENT_MISSING") {
      // 필수 약관에 모두 동의해야 보낼 수 있으므로, 그래도 빠졌다고 하면 BE의 약관 버전이 앱보다 새것이다
      setAgreeErr(
        requiredAgreed
          ? "약관이 새로 바뀌었어요. 앱을 새로고침한 뒤 다시 가입해 주세요."
          : (e.details[0]?.reason ?? e.message),
      );
      return true;
    }
    if (e.code !== "VALIDATION_FAILED") return false;
    const reason = (field: string) => e.details.find((d) => d.field === field)?.reason;
    setExtraErr(
      Object.fromEntries(
        EXTRA_FIELDS.flatMap((f) => (reason(f) ? [[f, reason(f)]] : [])),
      ) as Partial<Record<ExtraField, string>>,
    );
    const known: readonly string[] = EXTRA_FIELDS;
    return e.details.length > 0 && e.details.every((d) => known.includes(d.field));
  };

  return {
    profile,
    setProfile,
    gender,
    setGender,
    agree,
    setAgree,
    extraErr,
    setExtraErr,
    agreeErr,
    setAgreeErr,
    /** 선택 항목 형식이 맞고 필수 약관에 모두 동의했다 */
    ready: profileOk && requiredAgreed,
    payload,
    clearErrors,
    applyError,
  };
}
type ProfileForm = ReturnType<typeof useProfileForm>;

/** idPrefix로 화면마다 입력 id를 나눈다 */
export function ProfileFields({ form, idPrefix }: { form: ProfileForm; idPrefix: string }) {
  const { profile, setProfile, gender, setGender, extraErr, setExtraErr } = form;
  // 정적 HTML에 빌드한 날짜가 남지 않게 브라우저에서만 읽는다
  const maxBirth = useSyncExternalStore(noSubscribe, today, () => undefined);

  return (
    <div className="flex flex-col gap-6 border-t border-line pt-6">
      <div className="flex flex-col gap-1">
        <span className="text-[18px] font-bold text-ink">추가 정보</span>
        <span className="text-[15px] text-mute">선택 항목이에요. 비워 둬도 가입할 수 있어요.</span>
      </div>

      {PROFILE_INPUTS.map((p) => {
        const err = extraErr[p.field] ?? profileProblem(p.field, profile[p.field]);
        return (
          <div key={p.field} className="flex flex-col gap-2">
            <label htmlFor={`${idPrefix}-${p.field}`} className="text-[16px] font-bold text-ink">
              {p.label}
            </label>
            <TextField
              id={`${idPrefix}-${p.field}`}
              placeholder={p.placeholder}
              value={profile[p.field]}
              invalid={!!err}
              onChange={(e) => {
                setProfile((prev) => ({ ...prev, [p.field]: e.target.value }));
                setExtraErr((prev) => ({ ...prev, [p.field]: undefined }));
              }}
              autoComplete={p.autoComplete}
              inputMode={p.inputMode}
              maxLength={p.maxLength}
            />
            {err && <FieldError>{err}</FieldError>}
          </div>
        );
      })}

      <div className="flex flex-col gap-2">
        <label htmlFor={`${idPrefix}-birthDate`} className="text-[16px] font-bold text-ink">
          생년월일
        </label>
        <TextField
          id={`${idPrefix}-birthDate`}
          type="date"
          min="1900-01-01"
          max={maxBirth}
          value={profile.birthDate}
          invalid={!!extraErr.birthDate}
          onChange={(e) => {
            setProfile((prev) => ({ ...prev, birthDate: e.target.value }));
            setExtraErr((prev) => ({ ...prev, birthDate: undefined }));
          }}
          autoComplete="bday"
        />
        {extraErr.birthDate && <FieldError>{extraErr.birthDate}</FieldError>}
      </div>

      <div className="flex flex-col gap-2">
        <span className="text-[16px] font-bold text-ink">성별</span>
        <div className="grid grid-cols-2 gap-2.5">
          {GENDERS.map((g) => (
            <button
              key={g.value}
              type="button"
              aria-pressed={gender === g.value}
              onClick={() => {
                // 다시 누르면 선택을 지운다
                setGender((prev) => (prev === g.value ? null : g.value));
                setExtraErr((prev) => ({ ...prev, gender: undefined }));
              }}
              className={cn(
                "h-[60px] rounded-2xl border text-[17px] font-semibold",
                gender === g.value
                  ? "border-navy bg-ice-tint text-navy"
                  : "border-line-2 bg-white text-mute",
              )}
            >
              {g.label}
            </button>
          ))}
        </div>
        {extraErr.gender && <FieldError>{extraErr.gender}</FieldError>}
      </div>
    </div>
  );
}

export function AgreementFields({ form }: { form: ProfileForm }) {
  const { agree, setAgree, agreeErr, setAgreeErr } = form;
  const [termsOpen, setTermsOpen] = useState<TermsDoc | null>(null);
  const allAgreed = AGREEMENTS.every((a) => agree[a.type]);

  return (
    <div className="flex flex-col gap-3.5 border-t border-line pt-6">
      <button
        type="button"
        onClick={() => {
          setAgree(agreeAll(!allAgreed));
          setAgreeErr(null);
        }}
        className="flex items-center gap-3 text-[18px] font-bold text-ink"
        aria-pressed={allAgreed}
      >
        <span
          className={cn(
            "flex size-[26px] shrink-0 items-center justify-center rounded-lg border-[1.5px]",
            allAgreed ? "border-ice bg-ice text-ink" : "border-ash-2 bg-white text-white",
          )}
        >
          <Check className="size-4" strokeWidth={3} aria-hidden />
        </span>
        전체 동의
      </button>
      {AGREEMENTS.map((a) => (
        <div key={a.type} className="flex items-center gap-3 pl-1 text-[16px] text-ink">
          <button
            type="button"
            onClick={() => {
              setAgree((p) => ({ ...p, [a.type]: !p[a.type] }));
              setAgreeErr(null);
            }}
            aria-pressed={agree[a.type]}
            className="flex flex-1 items-center gap-3 text-left"
          >
            <span
              className={cn(
                "flex size-5 shrink-0 items-center justify-center",
                agree[a.type] ? "text-navy" : "text-line-3",
              )}
            >
              <Check className="size-[18px]" strokeWidth={2.6} aria-hidden />
            </span>
            <span className="flex-1">{a.label}</span>
          </button>
          {a.doc && (
            <button
              type="button"
              onClick={() => setTermsOpen(a.doc)}
              className="text-[15px] text-mute underline"
              aria-label={`${a.label} 보기`}
            >
              보기
            </button>
          )}
        </div>
      ))}
      {agreeErr && <FieldError>{agreeErr}</FieldError>}
      {termsOpen && (
        <TermsModal
          // 약관마다 스크롤 상태를 새로 센다
          key={termsOpen}
          doc={termsOpen}
          onClose={() => setTermsOpen(null)}
          onAgree={() => {
            setAgree((p) => ({ ...p, [termsOpen]: true }));
            setAgreeErr(null);
            setTermsOpen(null);
          }}
        />
      )}
    </div>
  );
}
