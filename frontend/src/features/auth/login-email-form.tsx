import { IconButton } from "@/components/ui/icon-button";
import { FieldError, Notice } from "@/components/ui/notice";
import { PillButton } from "@/components/ui/pill-button";
import { TextField } from "@/components/ui/text-field";

import type { LoginForm } from "./use-login-form";

/** 이메일·비밀번호 입력과 로그인 버튼. 잠금·혼잡 대기 시간을 버튼과 안내로 보여 준다 */
export function LoginEmailForm({
  form,
  onForgot,
  onBack,
}: {
  form: LoginForm;
  onForgot: () => void;
  onBack: () => void;
}) {
  const { busy, sessionChecked, waitLeft, lockLeft } = form;
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        form.submit();
      }}
    >
      <TextField
        type="email"
        placeholder="이메일"
        value={form.email}
        onChange={(e) => form.changeEmail(e.target.value)}
        autoComplete="email"
        maxLength={254}
      />
      <TextField
        type="password"
        placeholder="비밀번호"
        value={form.pw}
        onChange={(e) => form.changePw(e.target.value)}
        autoComplete="current-password"
        maxLength={256}
      />
      {form.error && lockLeft === 0 && <FieldError>{form.error}</FieldError>}
      {lockLeft > 0 && (
        <Notice tone="locked">
          <span>
            로그인 시도가 너무 많아요. <b className="tabular">{lockLeft}초</b> 후에 다시 시도해
            주세요.
          </span>
        </Notice>
      )}
      <button type="button" className="self-end text-[16px] text-mute underline" onClick={onForgot}>
        비밀번호를 잊었어요
      </button>
      <div className="mt-1 flex gap-3">
        <IconButton
          type="button"
          onClick={onBack}
          title="다른 방법으로 로그인"
          aria-label="다른 방법으로 로그인"
        />
        {/* 앱을 막 열었으면 내 계정 조회(최대 5초)가 끝날 때까지 기다린다는 걸 보여 준다 */}
        <PillButton
          type="submit"
          className="flex-1"
          busy={busy || !sessionChecked}
          disabled={!form.canLogin}
        >
          {busy
            ? "확인 중"
            : !sessionChecked
              ? "로그인 상태 확인 중"
              : waitLeft > 0
                ? `${waitLeft}초 후 다시 시도`
                : "로그인"}
        </PillButton>
      </div>
    </form>
  );
}
