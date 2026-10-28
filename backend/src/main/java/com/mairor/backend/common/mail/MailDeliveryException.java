package com.mairor.backend.common.mail;

/**
 * 메일을 보내지 못했다. 원인(SMTP 오류 등)은 {@code cause}에만 담고, 메시지에는 수신자 주소나 인증번호를 넣지 않는다. 호출한 쪽이 사용자에게 보일 오류(예:
 * 503)로 바꾼다.
 */
public class MailDeliveryException extends RuntimeException {

  public MailDeliveryException(String message) {
    super(message);
  }

  public MailDeliveryException(String message, Throwable cause) {
    super(message, cause);
  }
}
