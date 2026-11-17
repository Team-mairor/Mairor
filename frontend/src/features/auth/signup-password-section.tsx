import { FieldError } from "@/components/ui/notice";
import { TextField } from "@/components/ui/text-field";

import { RuleItem } from "./signup-parts";
import type { SignupPassword } from "./use-signup-password";

/** 비밀번호와 확인 입력. 규칙을 지켰는지 실시간으로 보여 준다 */
export function SignupPasswordSection({ password }: { password: SignupPassword }) {
  const { pw, pw2, rule, match, pwError, pw2Error } = password;
  return (
    <>
      <div className="flex flex-col gap-2">
        <label htmlFor="su-pw" className="text-[16px] font-bold text-ink">
          비밀번호
        </label>
        <TextField
          id="su-pw"
          type="password"
          placeholder="8~64자, 영문·숫자·특수문자 포함"
          value={pw}
          invalid={!!pwError}
          maxLength={64}
          onChange={(e) => password.changePw(e.target.value)}
          autoComplete="new-password"
        />
        <div className="flex flex-wrap gap-4 text-[15px]">
          <RuleItem ok={rule.len}>8~64자</RuleItem>
          <RuleItem ok={rule.mix}>영문 · 숫자 포함</RuleItem>
          <RuleItem ok={rule.spec}>특수문자 포함</RuleItem>
          <RuleItem ok={rule.bytes}>72바이트 이하 (한글 1자 3바이트)</RuleItem>
        </div>
        {pwError && <FieldError>{pwError}</FieldError>}
      </div>

      <div className="flex flex-col gap-2">
        <label htmlFor="su-pw2" className="text-[16px] font-bold text-ink">
          비밀번호 확인
        </label>
        <TextField
          id="su-pw2"
          type="password"
          placeholder="비밀번호를 한 번 더 입력해 주세요"
          value={pw2}
          invalid={(pw2.length > 0 && !match) || !!pw2Error}
          maxLength={64}
          onChange={(e) => password.changePw2(e.target.value)}
          autoComplete="new-password"
        />
        {pw2.length > 0 && !match && <FieldError>비밀번호가 일치하지 않아요.</FieldError>}
        {match && pw2Error && <FieldError>{pw2Error}</FieldError>}
      </div>
    </>
  );
}
