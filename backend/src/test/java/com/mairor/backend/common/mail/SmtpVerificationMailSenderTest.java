package com.mairor.backend.common.mail;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import jakarta.mail.Message;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.mail.MailSendException;
import org.springframework.mail.javamail.JavaMailSenderImpl;

/** 실제 SMTP 서버에 붙지 않고, 만들어진 메일 내용과 실패 처리를 확인한다. */
class SmtpVerificationMailSenderTest {

  /** 서버로 보내는 대신 만든 메일을 모아 두는 JavaMailSender. */
  private static class CapturingMailSender extends JavaMailSenderImpl {
    final List<MimeMessage> sent = new ArrayList<>();
    RuntimeException failure;

    @Override
    public void send(MimeMessage mimeMessage) {
      if (failure != null) {
        throw failure;
      }
      sent.add(mimeMessage);
    }
  }

  private final CapturingMailSender mailSender = new CapturingMailSender();
  private final SmtpVerificationMailSender sender =
      new SmtpVerificationMailSender(mailSender, "noreply@example.com", "Mairor");

  /** 멀티파트 메일에서 해당 타입(text/plain, text/html)의 본문을 찾는다. */
  private static String textOf(Part part, String mimeType) throws Exception {
    if (part.isMimeType(mimeType)) {
      return (String) part.getContent();
    }
    if (part.isMimeType("multipart/*")) {
      Multipart multipart = (Multipart) part.getContent();
      for (int i = 0; i < multipart.getCount(); i++) {
        String found = textOf(multipart.getBodyPart(i), mimeType);
        if (found != null) {
          return found;
        }
      }
    }
    return null;
  }

  @Test
  void sendsOneMailWithHtmlAndPlainTextVersions() throws Exception {
    sender.send("member@example.com", "123456", Duration.ofMinutes(10));

    assertThat(mailSender.sent).hasSize(1);
    MimeMessage mail = mailSender.sent.get(0);
    mail.saveChanges();
    assertThat(mail.getSubject()).isEqualTo("[Mairor] 이메일 인증번호");
    assertThat(((InternetAddress) mail.getRecipients(Message.RecipientType.TO)[0]).getAddress())
        .isEqualTo("member@example.com");
    InternetAddress from = (InternetAddress) mail.getFrom()[0];
    assertThat(from.getAddress()).isEqualTo("noreply@example.com");
    assertThat(from.getPersonal()).isEqualTo("Mairor");

    assertThat(textOf(mail, "text/html"))
        .contains("123456")
        .contains("10분")
        .contains("요청하지 않았다면")
        .doesNotContain("{{");
    assertThat(textOf(mail, "text/plain")).contains("123456").contains("10분");
  }

  @Test
  void describesValidityInSecondsWhenNotWholeMinutes() {
    assertThat(SmtpVerificationMailSender.body("123456", Duration.ofSeconds(90))).contains("90초");
    assertThat(SmtpVerificationMailSender.body("123456", Duration.ofMinutes(1))).contains("1분");
    assertThat(sender.html("123456", Duration.ofSeconds(90))).contains("90초");
    assertThat(sender.html("123456", Duration.ofMinutes(1))).contains("1분");
  }

  @Test
  void htmlEscapesTheValuesItInserts() {
    assertThat(sender.html("<b>1</b>", Duration.ofMinutes(10)))
        .contains("&lt;b&gt;1&lt;/b&gt;")
        .doesNotContain("<b>1</b>");
  }

  @Test
  void deliveryFailureBecomesMailDeliveryExceptionWithoutLeakingDetails() {
    mailSender.failure = new MailSendException("smtp down for member@example.com code 123456");

    assertThatThrownBy(() -> sender.send("member@example.com", "123456", Duration.ofMinutes(10)))
        .isInstanceOf(MailDeliveryException.class)
        .hasMessageNotContaining("member@example.com")
        .hasMessageNotContaining("123456")
        .hasCauseInstanceOf(MailSendException.class);
  }

  @Test
  void invalidRecipientBecomesMailDeliveryException() {
    assertThatThrownBy(() -> sender.send("not an address", "123456", Duration.ofMinutes(10)))
        .isInstanceOf(MailDeliveryException.class);
  }

  // ---- 비밀번호 재설정 ----

  @Test
  void resetCodeMailHasItsOwnSubjectAndBodyWithTheCode() throws Exception {
    sender.sendResetCode("member@example.com", "654321", Duration.ofMinutes(10));

    assertThat(mailSender.sent).hasSize(1);
    MimeMessage mail = mailSender.sent.get(0);
    mail.saveChanges();
    assertThat(mail.getSubject()).isEqualTo("[Mairor] 비밀번호 재설정 인증번호");
    assertThat(((InternetAddress) mail.getRecipients(Message.RecipientType.TO)[0]).getAddress())
        .isEqualTo("member@example.com");
    assertThat(((InternetAddress) mail.getFrom()[0]).getAddress()).isEqualTo("noreply@example.com");

    assertThat(textOf(mail, "text/html"))
        .contains("654321")
        .contains("10분")
        .contains("비밀번호 재설정")
        .contains("요청하지 않았다면")
        .doesNotContain("{{");
    assertThat(textOf(mail, "text/plain")).contains("654321").contains("10분").contains("비밀번호 재설정");
  }

  @Test
  void resetCodeHtmlEscapesTheValuesItInserts() {
    assertThat(sender.resetHtml("<b>1</b>", Duration.ofMinutes(10)))
        .contains("&lt;b&gt;1&lt;/b&gt;")
        .doesNotContain("<b>1</b>");
  }

  @Test
  void googleNoticeTellsToUseGoogleLoginAndCarriesNoCode() throws Exception {
    sender.sendGoogleAccountNotice("google@example.com");

    assertThat(mailSender.sent).hasSize(1);
    MimeMessage mail = mailSender.sent.get(0);
    mail.saveChanges();
    assertThat(mail.getSubject()).isEqualTo("[Mairor] 비밀번호 재설정 안내");
    assertThat(((InternetAddress) mail.getRecipients(Message.RecipientType.TO)[0]).getAddress())
        .isEqualTo("google@example.com");

    String html = textOf(mail, "text/html");
    assertThat(html).contains("Google로 로그인").contains("요청하지 않았다면").doesNotContain("{{");
    assertThat(html).doesNotContain("인증 번호");
    assertThat(textOf(mail, "text/plain")).contains("Google로 로그인");
  }

  @Test
  void resetMailFailuresBecomeMailDeliveryExceptionWithoutLeakingDetails() {
    mailSender.failure = new MailSendException("smtp down for member@example.com code 654321");

    assertThatThrownBy(
            () -> sender.sendResetCode("member@example.com", "654321", Duration.ofMinutes(10)))
        .isInstanceOf(MailDeliveryException.class)
        .hasMessageNotContaining("member@example.com")
        .hasMessageNotContaining("654321")
        .hasCauseInstanceOf(MailSendException.class);
    assertThatThrownBy(() -> sender.sendGoogleAccountNotice("google@example.com"))
        .isInstanceOf(MailDeliveryException.class)
        .hasMessageNotContaining("google@example.com");
  }
}
