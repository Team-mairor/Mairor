package com.mairor.backend.users.support;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

/** 인증 정책 기본값이 바인딩되고 인메모리 저장소와 해시 빈이 만들어지는지 확인한다. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(properties = "app.security.allowed-origins=http://localhost:3000")
class EmailVerificationConfigTest {

  @Autowired private EmailVerificationProperties properties;
  @Autowired private EmailVerificationStore store;
  @Autowired private VerificationHasher hasher;

  @Test
  void defaultsAreBound() {
    assertThat(properties.codeTtl()).isEqualTo(Duration.ofMinutes(10));
    assertThat(properties.resendCooldown()).isEqualTo(Duration.ofSeconds(60));
    assertThat(properties.hourlyLimit()).isEqualTo(5);
    assertThat(properties.maxAttempts()).isEqualTo(5);
    assertThat(properties.tokenTtl()).isEqualTo(Duration.ofMinutes(30));
  }

  @Test
  void theStoreIsTheInMemoryOneConfiguredWithTheProperties() {
    assertThat(store).isInstanceOf(InMemoryEmailVerificationStore.class);
    var now = java.time.Instant.now();

    assertThat(store.reserveSend("config-test@example.com", now).isAllowed()).isTrue();
    // 설정의 재발송 간격(60초) 안이라 막힌다
    assertThat(store.reserveSend("config-test@example.com", now.plusSeconds(30)).isAllowed())
        .isFalse();
  }

  @Test
  void hasherIsAvailable() {
    assertThat(hasher.hashToken("abc")).hasSize(64);
  }
}
