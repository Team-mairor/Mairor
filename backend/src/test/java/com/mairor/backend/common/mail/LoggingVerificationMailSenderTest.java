package com.mairor.backend.common.mail;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

@ExtendWith(OutputCaptureExtension.class)
class LoggingVerificationMailSenderTest {

  @Test
  void logsTheCodeButMasksTheRecipient(CapturedOutput output) {
    new LoggingVerificationMailSender()
        .send("member@example.com", "123456", Duration.ofMinutes(10));

    assertThat(output.getAll())
        .contains("123456")
        .contains("m***@example.com")
        .contains("10분")
        .doesNotContain("member@example.com");
  }

  @Test
  void masksUnusualAddressesSafely() {
    assertThat(LoggingVerificationMailSender.mask("a@example.com")).isEqualTo("a***@example.com");
    assertThat(LoggingVerificationMailSender.mask("@example.com")).isEqualTo("***");
    assertThat(LoggingVerificationMailSender.mask("no-at-sign")).isEqualTo("***");
    assertThat(LoggingVerificationMailSender.mask(null)).isEqualTo("***");
  }
}
