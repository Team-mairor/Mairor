package com.mairor.backend.common.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.users.support.AuthenticatedUser;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.serializer.RedisSerializer;
import org.springframework.data.redis.serializer.SerializationException;

/**
 * 세션 속성을 바이트로 바꾸는 직렬화기. 읽는 쪽의 실패만 {@link UnreadableSessionException} 이고, 저장하는 쪽의 실패는 그대로 {@link
 * SerializationException} 이어야 한다. 둘을 같은 예외로 두면 서버 버그가 "로그인 만료"로 보인다.
 */
class SessionSerializerConfigTest {

  private final RedisSerializer<Object> serializer =
      SessionSerializerConfig.create(getClass().getClassLoader());

  @Test
  void aValueSurvivesTheRoundTrip() {
    AuthenticatedUser user = new AuthenticatedUser(UUID.randomUUID(), "member@example.com");
    Instant loggedInAt = Instant.parse("2026-10-29T03:00:00Z");

    assertThat(serializer.deserialize(serializer.serialize(user))).isEqualTo(user);
    assertThat(serializer.deserialize(serializer.serialize(loggedInAt))).isEqualTo(loggedInAt);
    assertThat(serializer.deserialize(serializer.serialize("text"))).isEqualTo("text");
  }

  @Test
  void aValueThatCannotBeSerializedFailsAsASerializationErrorNotAnUnreadableSession() {
    assertThatThrownBy(() -> serializer.serialize(new Object()))
        .isInstanceOf(SerializationException.class)
        .satisfies(
            e -> assertThat(causes(e)).noneMatch(UnreadableSessionException.class::isInstance));
  }

  @Test
  void bytesThatCannotBeReadFailAsAnUnreadableSession() {
    assertThatThrownBy(() -> serializer.deserialize(new byte[] {0}))
        .isInstanceOf(UnreadableSessionException.class);
  }

  @Test
  void aCutOffValueIsAnUnreadableSession() {
    byte[] truncated = Arrays.copyOf(serializer.serialize(Instant.now()), 10);

    assertThatThrownBy(() -> serializer.deserialize(truncated))
        .isInstanceOf(UnreadableSessionException.class);
  }

  private static List<Throwable> causes(Throwable e) {
    List<Throwable> chain = new ArrayList<>();
    for (Throwable t = e; t != null && chain.size() < 20; t = t.getCause()) {
      chain.add(t);
    }
    return chain;
  }
}
