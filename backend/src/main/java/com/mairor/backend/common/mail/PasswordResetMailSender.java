package com.mairor.backend.common.mail;

import java.time.Duration;

/**
 * 비밀번호 재설정 메일 발송. 구현체가 발송 방식(Gmail SMTP, 개발용 로그 등)을 정하고, 동기로 보내며 실패하면 {@link
 * MailDeliveryException}을 던진다. 미가입 이메일에는 아무것도 보내지 않으므로 그런 메서드는 없다(호출자가 정한다).
 */
public interface PasswordResetMailSender {

  /**
   * 비밀번호 재설정 인증번호를 메일로 보낸다 (자체 가입 계정).
   *
   * @param to 받는 사람의 정규화한 이메일
   * @param code 인증번호(6자리 숫자)
   * @param validFor 인증번호가 유효한 시간 (메일 본문에 안내한다)
   * @throws MailDeliveryException 발송하지 못했을 때
   */
  void sendResetCode(String to, String code, Duration validFor);

  /**
   * 비밀번호가 없는 Google 로그인 전용 계정에, 인증번호 대신 "Google 로 로그인하세요" 안내를 보낸다. 계정을 연결하거나 바꾸지 않는다.
   *
   * @param to 받는 사람의 정규화한 이메일
   * @throws MailDeliveryException 발송하지 못했을 때
   */
  void sendGoogleAccountNotice(String to);
}
