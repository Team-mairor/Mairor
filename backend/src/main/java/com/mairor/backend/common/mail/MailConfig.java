package com.mairor.backend.common.mail;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.mail.autoconfigure.MailProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.util.StringUtils;

/**
 * 인증 메일(가입 인증번호, 비밀번호 재설정) 발송기를 고른다. 셋 중 하나만 {@link AuthMailSender} 빈이 되고, {@link
 * VerificationMailSender}와 {@link PasswordResetMailSender} 어느 쪽으로 주입받아도 이 빈이 온다.
 *
 * <ul>
 *   <li>{@code app.mail.enabled=true}: {@link SmtpVerificationMailSender}. SMTP 계정({@code
 *       spring.mail.username/password})이 없으면 시작 단계에서 실패한다.
 *   <li>꺼짐 + 운영 외 프로파일: {@link LoggingVerificationMailSender} (코드를 로그로만 남김)
 *   <li>꺼짐 + {@code prod}: {@link UnavailableVerificationMailSender} (항상 실패)
 * </ul>
 */
@Configuration
public class MailConfig {

  @Bean
  @ConditionalOnProperty(prefix = "app.mail", name = "enabled", havingValue = "true")
  AuthMailSender smtpVerificationMailSender(
      JavaMailSender mailSender, AppMailProperties app, MailProperties smtp) {
    if (!StringUtils.hasText(smtp.getUsername()) || !StringUtils.hasText(smtp.getPassword())) {
      throw new IllegalStateException(
          "app.mail.enabled=true 인데 SMTP 계정이 비어 있습니다. MAIL_USERNAME, MAIL_PASSWORD 를 설정하세요.");
    }
    String from = StringUtils.hasText(app.from()) ? app.from() : smtp.getUsername();
    String fromName = StringUtils.hasText(app.fromName()) ? app.fromName() : "Mairor";
    return new SmtpVerificationMailSender(mailSender, from, fromName);
  }

  @Bean
  @Profile("!prod")
  @ConditionalOnProperty(
      prefix = "app.mail",
      name = "enabled",
      havingValue = "false",
      matchIfMissing = true)
  AuthMailSender loggingVerificationMailSender() {
    return new LoggingVerificationMailSender();
  }

  @Bean
  @Profile("prod")
  @ConditionalOnProperty(
      prefix = "app.mail",
      name = "enabled",
      havingValue = "false",
      matchIfMissing = true)
  AuthMailSender unavailableVerificationMailSender() {
    return new UnavailableVerificationMailSender();
  }
}
