package com.mairor.backend.common.mail;

import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * 메일을 보내지 않고 내용을 로그로만 남기는 개발·테스트용 발송기. 메일 계정 없이도 가입·비밀번호 재설정 흐름을 끝까지 확인할 수 있다.
 *
 * <p>운영(prod)에서는 만들어지지 않는다({@link MailConfig}). 받는 사람 주소는 일부만 보이게 가린다. 인증번호는 확인용으로 그대로 남긴다.
 */
public class LoggingVerificationMailSender implements AuthMailSender {

  private static final Logger log = LoggerFactory.getLogger(LoggingVerificationMailSender.class);

  @Override
  public void send(String to, String code, Duration validFor) {
    log.info(
        "[개발용 메일 발송] 실제 메일은 보내지 않습니다. 받는 사람={}, 인증번호={}, 유효 시간={}",
        mask(to),
        code,
        VerificationMailSender.describe(validFor));
  }

  @Override
  public void sendResetCode(String to, String code, Duration validFor) {
    log.info(
        "[개발용 메일 발송] 실제 메일은 보내지 않습니다. 비밀번호 재설정 인증번호. 받는 사람={}, 인증번호={}, 유효 시간={}",
        mask(to),
        code,
        VerificationMailSender.describe(validFor));
  }

  @Override
  public void sendGoogleAccountNotice(String to) {
    log.info("[개발용 메일 발송] 실제 메일은 보내지 않습니다. 비밀번호 재설정 대신 Google 로그인 안내. 받는 사람={}", mask(to));
  }

  /** {@code member@example.com} → {@code m***@example.com}. */
  static String mask(String email) {
    int at = email == null ? -1 : email.indexOf('@');
    if (at < 1) {
      return "***";
    }
    return email.charAt(0) + "***" + email.substring(at);
  }
}
