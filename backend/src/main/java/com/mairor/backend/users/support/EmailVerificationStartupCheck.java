package com.mairor.backend.users.support;

import com.mairor.backend.common.mail.AppMailProperties;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

/**
 * 가입에 이메일 인증을 요구하는 prod 환경에서 메일 발송({@code MAIL_ENABLED=true}, SMTP 계정은 {@code MailConfig}가 확인)과
 * 인증번호 해시 비밀키({@code EMAIL_VERIFICATION_SECRET})가 설정됐는지 기동할 때 확인한다. 빠진 채 뜨면 배포 뒤에야 가입 실패로 드러난다.
 */
@Component
public class EmailVerificationStartupCheck {

  public EmailVerificationStartupCheck(
      SignupProperties signup,
      AppMailProperties mail,
      EmailVerificationProperties verification,
      Environment environment) {
    if (!signup.requireEmailVerification() || !environment.acceptsProfiles(Profiles.of("prod"))) {
      return;
    }
    if (!mail.enabled()) {
      throw new IllegalStateException(
          "가입 이메일 인증을 요구하는데(SIGNUP_REQUIRE_EMAIL_VERIFICATION=true) 메일 발송이 꺼져 있습니다. "
              + "MAIL_ENABLED=true 와 MAIL_USERNAME, MAIL_PASSWORD 를 설정하세요.");
    }
    if (!StringUtils.hasText(verification.secret())) {
      throw new IllegalStateException(
          "가입 이메일 인증을 요구하는데(SIGNUP_REQUIRE_EMAIL_VERIFICATION=true) "
              + "EMAIL_VERIFICATION_SECRET 이 비어 있습니다.");
    }
  }
}
