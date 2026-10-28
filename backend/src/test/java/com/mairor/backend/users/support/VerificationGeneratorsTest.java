package com.mairor.backend.users.support;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.users.dto.request.EmailVerificationConfirmRequest;
import com.mairor.backend.users.dto.request.EmailVerificationRequest;
import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;

class VerificationGeneratorsTest {

  @Test
  void code_isAlwaysSixDigits() {
    VerificationCodeGenerator generator = new VerificationCodeGenerator();

    for (int i = 0; i < 2000; i++) {
      assertThat(generator.generate()).matches("\\d{6}");
    }
  }

  @Test
  void code_keepsLeadingZeros_andVaries() {
    VerificationCodeGenerator generator = new VerificationCodeGenerator();
    Set<String> seen = new HashSet<>();
    boolean leadingZero = false;
    for (int i = 0; i < 5000; i++) {
      String code = generator.generate();
      seen.add(code);
      leadingZero |= code.startsWith("0");
    }

    assertThat(seen.size()).isGreaterThan(4000);
    assertThat(leadingZero).isTrue();
  }

  @Test
  void token_isUrlSafeAnd43CharsLong_andUnique() {
    VerificationTokens tokens = new VerificationTokens();
    Set<String> seen = new HashSet<>();

    for (int i = 0; i < 1000; i++) {
      String token = tokens.generate();
      assertThat(token).matches("[A-Za-z0-9_-]{43}");
      seen.add(token);
    }

    assertThat(seen).hasSize(1000);
  }

  @Test
  void requestsNormalizeTheEmailAndMaskThemselves() {
    var send = new EmailVerificationRequest("  Member@Example.COM ");
    var confirm = new EmailVerificationConfirmRequest("  Member@Example.COM ", "123456");

    assertThat(send.email()).isEqualTo("member@example.com");
    assertThat(confirm.email()).isEqualTo("member@example.com");
    assertThat(send.toString()).doesNotContain("member");
    assertThat(confirm.toString()).doesNotContain("member").doesNotContain("123456");
  }
}
