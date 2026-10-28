package com.mairor.backend.common.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;
import java.io.IOException;
import java.io.InputStream;
import java.io.UnsupportedEncodingException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.web.util.HtmlUtils;

/**
 * SMTP(Gmail)로 인증번호 메일을 동기로 보낸다. HTML 본문({@value #TEMPLATE_PATH})과 HTML 을 못 보는 클라이언트를 위한 평문 본문을 함께
 * 담는다. 타임아웃은 {@code spring.mail.properties.mail.smtp.*}에서 정한다. 실패 원인은 {@code cause}로만 전달하고, 메시지·로그에
 * 받는 사람 주소나 인증번호를 넣지 않는다.
 */
public class SmtpVerificationMailSender implements VerificationMailSender {

  static final String SUBJECT = "[Mairor] 이메일 인증번호";
  static final String TEMPLATE_PATH = "mail/verification-code.html";

  private final JavaMailSender mailSender;
  private final InternetAddress from;
  private final String htmlTemplate;

  public SmtpVerificationMailSender(
      JavaMailSender mailSender, String fromAddress, String fromName) {
    this.mailSender = mailSender;
    try {
      this.from = new InternetAddress(fromAddress, fromName, StandardCharsets.UTF_8.name());
    } catch (UnsupportedEncodingException e) {
      throw new IllegalStateException("보내는 사람 정보를 만들 수 없습니다.", e);
    }
    this.htmlTemplate = loadTemplate();
  }

  @Override
  public void send(String to, String code, Duration validFor) {
    try {
      MimeMessage message = mailSender.createMimeMessage();
      MimeMessageHelper helper =
          new MimeMessageHelper(message, true, StandardCharsets.UTF_8.name());
      helper.setFrom(from);
      helper.setTo(to);
      helper.setSubject(SUBJECT);
      helper.setText(body(code, validFor), html(code, validFor));
      mailSender.send(message);
    } catch (MailException | MessagingException e) {
      throw new MailDeliveryException("인증번호 메일을 보내지 못했습니다.", e);
    }
  }

  String html(String code, Duration validFor) {
    return htmlTemplate
        .replace("{{code}}", HtmlUtils.htmlEscape(code))
        .replace("{{validFor}}", HtmlUtils.htmlEscape(VerificationMailSender.describe(validFor)));
  }

  private static String loadTemplate() {
    try (InputStream in = new ClassPathResource(TEMPLATE_PATH).getInputStream()) {
      return new String(in.readAllBytes(), StandardCharsets.UTF_8);
    } catch (IOException e) {
      throw new IllegalStateException("인증번호 메일 템플릿을 읽을 수 없습니다: " + TEMPLATE_PATH, e);
    }
  }

  static String body(String code, Duration validFor) {
    return """
        Mairor 이메일 인증번호입니다.

        인증번호: %s
        %s 내에 인증해주세요.

        """
        .formatted(code, VerificationMailSender.describe(validFor));
  }
}
