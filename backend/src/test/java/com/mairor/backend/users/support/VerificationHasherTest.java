package com.mairor.backend.users.support;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

@ExtendWith(OutputCaptureExtension.class)
class VerificationHasherTest {

  private final VerificationHasher hasher = new VerificationHasher("test-secret");

  @Test
  void codeHashIsDeterministicHex() {
    String hash = hasher.hashCode("member@example.com", "123456");

    assertThat(hash).isEqualTo(hasher.hashCode("member@example.com", "123456"));
    assertThat(hash).matches("[0-9a-f]{64}").doesNotContain("123456");
  }

  @Test
  void codeHashDependsOnEmailCodeAndSecret() {
    String base = hasher.hashCode("member@example.com", "123456");

    assertThat(hasher.hashCode("other@example.com", "123456")).isNotEqualTo(base);
    assertThat(hasher.hashCode("member@example.com", "654321")).isNotEqualTo(base);
    assertThat(new VerificationHasher("another-secret").hashCode("member@example.com", "123456"))
        .isNotEqualTo(base);
  }

  @Test
  void codeAndEmailBoundaryCannotBeShifted() {
    // 이메일과 코드를 이어 붙여도 서로 다른 입력은 서로 다른 해시여야 한다
    assertThat(hasher.hashCode("a@example.com", "1234:56"))
        .isNotEqualTo(hasher.hashCode("a@example.com:1234", "56"));
  }

  @Test
  void decoyCodeHashLooksLikeARealOneButIsDifferentEveryTime() {
    String first = hasher.decoyCodeHash();
    String second = hasher.decoyCodeHash();

    // 실제 해시와 같은 모양이라 저장소에서 꺼내 봐도 구별되지 않고, 매번 달라서 맞힐 수 없다
    assertThat(first).matches("[0-9a-f]{64}");
    assertThat(second).matches("[0-9a-f]{64}");
    assertThat(first).isNotEqualTo(second);
  }

  @Test
  void decoyCodeHashDoesNotMatchAnySixDigitCode() {
    String decoy = hasher.decoyCodeHash();

    for (int code = 0; code < 1_000; code++) {
      assertThat(hasher.hashCode("member@example.com", "%06d".formatted(code))).isNotEqualTo(decoy);
    }
  }

  @Test
  void tokenHashIsSha256() {
    // SHA-256("abc") 의 알려진 값
    assertThat(hasher.hashToken("abc"))
        .isEqualTo("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  }

  @Test
  void tokenHashDoesNotDependOnTheSecret() {
    assertThat(new VerificationHasher("another-secret").hashToken("abc"))
        .isEqualTo(hasher.hashToken("abc"));
  }

  @Test
  void blankSecret_createsARandomOneAndWarns(CapturedOutput output) {
    VerificationHasher first = new VerificationHasher("");
    VerificationHasher second = new VerificationHasher("   ");

    assertThat(output.getAll()).contains("EMAIL_VERIFICATION_SECRET");
    // 같은 인스턴스 안에서는 일관되고, 인스턴스마다 다르다
    assertThat(first.hashCode("a@example.com", "123456"))
        .isEqualTo(first.hashCode("a@example.com", "123456"));
    assertThat(first.hashCode("a@example.com", "123456"))
        .isNotEqualTo(second.hashCode("a@example.com", "123456"));
  }

  @Test
  void nullSecret_isTreatedAsBlank() {
    assertThat(new VerificationHasher((String) null).hashCode("a@example.com", "123456"))
        .matches("[0-9a-f]{64}");
  }
}
