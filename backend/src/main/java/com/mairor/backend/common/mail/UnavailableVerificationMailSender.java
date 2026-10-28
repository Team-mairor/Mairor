package com.mairor.backend.common.mail;

import java.time.Duration;

/**
 * 운영(prod)에서 메일 발송을 설정하지 않았을 때 쓰는 발송기. 아무것도 보내지 않고 항상 실패해서, 인증번호가 로그에 찍히거나 메일이 간 것처럼 보이는 일을 막는다.
 *
 * <p>메일 발송을 켜지 않은 채 배포해도 앱은 뜬다. 이메일 인증을 요구하도록 설정했는데 메일 발송이 꺼져 있으면 시작 단계에서 실패시킨다({@code
 * EmailVerificationStartupCheck}).
 */
public class UnavailableVerificationMailSender implements VerificationMailSender {

  @Override
  public void send(String to, String code, Duration validFor) {
    throw new MailDeliveryException("메일 발송이 설정되지 않았습니다. (app.mail.enabled=false)");
  }
}
