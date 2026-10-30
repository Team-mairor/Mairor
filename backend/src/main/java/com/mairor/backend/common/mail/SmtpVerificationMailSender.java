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
 * SMTP(Gmail)로 인증 메일(가입 인증번호, 비밀번호 재설정 인증번호, Google 전용 계정 안내)을 동기로 보낸다. 메일마다 HTML 본문({@code
 * mail/*.html})과 HTML 을 못 보는 클라이언트를 위한 평문 본문을 함께 담는다. 타임아웃은 {@code
 * spring.mail.properties.mail.smtp.*}에서 정한다. 실패 원인은 {@code cause}로만 전달하고, 메시지·로그에 받는 사람 주소나 인증번호를
 * 넣지 않는다.
 */
public class SmtpVerificationMailSender implements AuthMailSender {

  static final String SUBJECT = "[Mairor] 이메일 인증번호";
  static final String TEMPLATE_PATH = "mail/verification-code.html";
  static final String RESET_SUBJECT = "[Mairor] 비밀번호 재설정 인증번호";
  static final String RESET_TEMPLATE_PATH = "mail/password-reset-code.html";
  static final String GOOGLE_NOTICE_SUBJECT = "[Mairor] 비밀번호 재설정 안내";
  static final String GOOGLE_NOTICE_TEMPLATE_PATH = "mail/google-account-notice.html";

  private static final String GOOGLE_NOTICE_BODY =
      """
      Mairor 비밀번호 재설정 안내입니다.

      이 이메일은 Google 로그인으로 가입돼 있어 비밀번호가 없습니다.
      mairor 로그인 화면에서 'Google로 로그인'을 눌러 주세요.

      본인이 요청하지 않았다면 이 메일을 무시해 주세요. 계정에는 아무 변화가 없습니다.
      """;

  private final JavaMailSender mailSender;
  private final InternetAddress from;
  private final String htmlTemplate;
  private final String resetHtmlTemplate;
  private final String googleNoticeHtml;

  public SmtpVerificationMailSender(
      JavaMailSender mailSender, String fromAddress, String fromName) {
    this.mailSender = mailSender;
    try {
      this.from = new InternetAddress(fromAddress, fromName, StandardCharsets.UTF_8.name());
    } catch (UnsupportedEncodingException e) {
      throw new IllegalStateException("보내는 사람 정보를 만들 수 없습니다.", e);
    }
    this.htmlTemplate = loadTemplate(TEMPLATE_PATH);
    this.resetHtmlTemplate = loadTemplate(RESET_TEMPLATE_PATH);
    this.googleNoticeHtml = loadTemplate(GOOGLE_NOTICE_TEMPLATE_PATH);
  }

  @Override
  public void send(String to, String code, Duration validFor) {
    deliver(to, SUBJECT, body(code, validFor), html(code, validFor), "인증번호 메일을 보내지 못했습니다.");
  }

  @Override
  public void sendResetCode(String to, String code, Duration validFor) {
    deliver(
        to,
        RESET_SUBJECT,
        resetBody(code, validFor),
        resetHtml(code, validFor),
        "비밀번호 재설정 메일을 보내지 못했습니다.");
  }

  @Override
  public void sendGoogleAccountNotice(String to) {
    deliver(
        to,
        GOOGLE_NOTICE_SUBJECT,
        GOOGLE_NOTICE_BODY,
        googleNoticeHtml,
        "비밀번호 재설정 안내 메일을 보내지 못했습니다.");
  }

  /** 메일 한 통을 만들어 보낸다. 실패 메시지에는 받는 사람과 본문 내용을 넣지 않는다. */
  private void deliver(String to, String subject, String plain, String html, String failure) {
    try {
      MimeMessage message = mailSender.createMimeMessage();
      MimeMessageHelper helper =
          new MimeMessageHelper(message, true, StandardCharsets.UTF_8.name());
      helper.setFrom(from);
      helper.setTo(to);
      helper.setSubject(subject);
      helper.setText(plain, html);
      mailSender.send(message);
    } catch (MailException | MessagingException e) {
      throw new MailDeliveryException(failure, e);
    }
  }

  String html(String code, Duration validFor) {
    return fill(htmlTemplate, code, validFor);
  }

  String resetHtml(String code, Duration validFor) {
    return fill(resetHtmlTemplate, code, validFor);
  }

  private static String fill(String template, String code, Duration validFor) {
    return template
        .replace("{{code}}", HtmlUtils.htmlEscape(code))
        .replace("{{validFor}}", HtmlUtils.htmlEscape(VerificationMailSender.describe(validFor)));
  }

  private static String loadTemplate(String path) {
    try (InputStream in = new ClassPathResource(path).getInputStream()) {
      return new String(in.readAllBytes(), StandardCharsets.UTF_8);
    } catch (IOException e) {
      throw new IllegalStateException("메일 템플릿을 읽을 수 없습니다: " + path, e);
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

  static String resetBody(String code, Duration validFor) {
    return """
        Mairor 비밀번호 재설정 인증번호입니다.

        인증번호: %s
        %s 내에 입력해 주세요.

        본인이 요청하지 않았다면 이 메일을 무시해 주세요. 비밀번호는 바뀌지 않습니다.
        비밀번호를 바꾸면 로그인된 모든 기기에서 로그아웃됩니다.
        """
        .formatted(code, VerificationMailSender.describe(validFor));
  }
}
