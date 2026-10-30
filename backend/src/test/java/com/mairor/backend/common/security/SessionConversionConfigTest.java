package com.mairor.backend.common.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.users.support.AuthenticatedUser;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.core.convert.ConversionFailedException;
import org.springframework.core.convert.support.GenericConversionService;
import org.springframework.core.serializer.support.SerializationFailedException;

/**
 * 세션 속성을 바이트로 바꾸는 변환 서비스. 읽는 쪽의 실패만 {@link UnreadableSessionException} 이고, 저장하는 쪽의 실패는 그대로 {@link
 * SerializationFailedException} 이어야 한다. 둘을 같은 예외로 두면 서버 버그가 "로그인 만료"로 보인다.
 */
class SessionConversionConfigTest {

  private final GenericConversionService conversion =
      SessionConversionConfig.create(getClass().getClassLoader());

  private byte[] serialize(Object value) {
    return conversion.convert(value, byte[].class);
  }

  private Object deserialize(byte[] bytes) {
    return conversion.convert(bytes, Object.class);
  }

  @Test
  void aValueSurvivesTheRoundTrip() {
    AuthenticatedUser user = new AuthenticatedUser(UUID.randomUUID(), "member@example.com");
    Instant loggedInAt = Instant.parse("2026-10-29T03:00:00Z");

    assertThat(deserialize(serialize(user))).isEqualTo(user);
    assertThat(deserialize(serialize(loggedInAt))).isEqualTo(loggedInAt);
    assertThat(deserialize(serialize("text"))).isEqualTo("text");
  }

  @Test
  void aValueThatCannotBeSerializedFailsAsASerializationErrorNotAnUnreadableSession() {
    assertThatThrownBy(() -> serialize(new Object()))
        .isInstanceOf(ConversionFailedException.class)
        .satisfies(
            e -> {
              assertThat(causes(e)).anyMatch(c -> c instanceof SerializationFailedException);
              assertThat(causes(e)).noneMatch(c -> c instanceof UnreadableSessionException);
            });
  }

  @Test
  void bytesThatCannotBeReadFailAsAnUnreadableSession() {
    assertThatThrownBy(() -> deserialize(new byte[] {0}))
        .satisfies(
            e -> assertThat(causes(e)).anyMatch(c -> c instanceof UnreadableSessionException));
    assertThatThrownBy(() -> deserialize(new byte[0]))
        .satisfies(
            e -> assertThat(causes(e)).anyMatch(c -> c instanceof UnreadableSessionException));
  }

  @Test
  void aClassThatNoLongerExistsIsAnUnreadableSession() {
    // 다른 버전이 저장한 값: 직렬화 데이터가 읽을 수 없는 클래스를 가리킨다
    byte[] foreign = serialize("text");
    foreign[foreign.length - 1] ^= 0x7f;
    byte[] truncated = java.util.Arrays.copyOf(serialize(Instant.now()), 10);

    assertThatThrownBy(() -> deserialize(truncated))
        .satisfies(
            e -> assertThat(causes(e)).anyMatch(c -> c instanceof UnreadableSessionException));
  }

  private static java.util.List<Throwable> causes(Throwable e) {
    java.util.List<Throwable> chain = new java.util.ArrayList<>();
    for (Throwable t = e; t != null && chain.size() < 20; t = t.getCause()) {
      chain.add(t);
    }
    return chain;
  }
}
