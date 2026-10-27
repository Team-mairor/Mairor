package com.mairor.backend.common.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.password.PasswordEncoder;

class PasswordEncoderConfigTest {

  private final PasswordEncoder encoder = new PasswordEncoderConfig().passwordEncoder();

  @Test
  void encode_prefixesBcryptIdAndHidesPlaintext() {
    String hash = encoder.encode("ExampleOnly!2026");

    assertThat(hash).startsWith("{bcrypt}$2").doesNotContain("ExampleOnly");
  }

  @Test
  void matches_acceptsOnlyTheOriginalPassword() {
    String hash = encoder.encode("ExampleOnly!2026");

    assertThat(encoder.matches("ExampleOnly!2026", hash)).isTrue();
    assertThat(encoder.matches("WrongPassword!2026", hash)).isFalse();
  }

  @Test
  void encode_acceptsExactly72BytesAndRefusesMore() {
    assertThat(encoder.encode("a".repeat(72))).startsWith("{bcrypt}$2");

    assertThatThrownBy(() -> encoder.encode("a".repeat(73)))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("72 bytes");
  }

  /**
   * 라이브러리 특성을 기록해 두는 테스트: {@code matches}는 72바이트 뒤를 무시한다. 그래서 가입뿐 아니라 로그인에서도 72바이트를 넘는 입력을 먼저 거절해야
   * 한다 (앞 72바이트만 맞는 긴 입력으로 로그인되는 것을 막기 위해).
   */
  @Test
  void matches_ignoresBytesBeyond72_soLoginMustRejectLongInputItself() {
    String hash = encoder.encode("a".repeat(72));

    assertThat(encoder.matches("a".repeat(73), hash)).isTrue();
  }

  @Test
  void encode_producesDifferentHashesForSamePassword() {
    assertThat(encoder.encode("ExampleOnly!2026")).isNotEqualTo(encoder.encode("ExampleOnly!2026"));
  }
}
