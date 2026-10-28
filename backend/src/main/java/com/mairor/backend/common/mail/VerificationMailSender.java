package com.mairor.backend.common.mail;

import java.time.Duration;

/**
 * 이메일 인증번호 메일 발송. 구현체가 발송 방식(Gmail SMTP, 개발용 로그 등)을 정하고, 동기로 보내며 실패하면 {@link
 * MailDeliveryException}을 던진다.
 */
public interface VerificationMailSender {

  /**
   * 인증번호를 메일로 보낸다.
   *
   * @param to 받는 사람의 정규화한 이메일
   * @param code 인증번호(6자리 숫자)
   * @param validFor 인증번호가 유효한 시간 (메일 본문에 안내한다)
   * @throws MailDeliveryException 발송하지 못했을 때
   */
  void send(String to, String code, Duration validFor);

  /** 유효 시간을 사람이 읽는 말로 바꾼다. 1분 단위로 떨어지면 "10분", 아니면 "90초". */
  static String describe(Duration validFor) {
    long seconds = validFor.toSeconds();
    return seconds >= 60 && seconds % 60 == 0 ? (seconds / 60) + "분" : seconds + "초";
  }
}
