package com.mairor.backend.common.mail;

/**
 * 인증 관련 메일(가입 이메일 인증, 비밀번호 재설정)을 모두 보내는 발송기. 발송 방식(SMTP·로그·발송 불가)마다 구현체가 하나이고, {@link MailConfig}가
 * 그중 하나만 이 타입의 빈으로 만든다. 그래서 {@link VerificationMailSender}와 {@link PasswordResetMailSender} 어느 쪽으로
 * 주입받아도 같은 발송기가 온다.
 */
public interface AuthMailSender extends VerificationMailSender, PasswordResetMailSender {}
