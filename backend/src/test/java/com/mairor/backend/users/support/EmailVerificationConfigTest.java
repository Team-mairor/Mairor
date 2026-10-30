package com.mairor.backend.users.support;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

/** 인증 정책 기본값이 바인딩되고 용도별 인메모리 저장소와 해시 빈이 만들어지는지 확인한다. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(properties = "app.security.allowed-origins=http://localhost:3000")
class EmailVerificationConfigTest {

  @Autowired private EmailVerificationProperties properties;
  @Autowired private PasswordResetProperties resetProperties;

  @Autowired
  @Qualifier(EmailVerificationStoreConfig.SIGNUP)
  private EmailVerificationStore store;

  @Autowired
  @Qualifier(EmailVerificationStoreConfig.PASSWORD_RESET)
  private EmailVerificationStore resetStore;

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
  void passwordResetDefaultsAreBoundSeparately() {
    assertThat(resetProperties.codeTtl()).isEqualTo(Duration.ofMinutes(10));
    assertThat(resetProperties.resendCooldown()).isEqualTo(Duration.ofSeconds(60));
    assertThat(resetProperties.hourlyLimit()).isEqualTo(5);
    assertThat(resetProperties.maxAttempts()).isEqualTo(5);
    assertThat(resetProperties.tokenTtl()).isEqualTo(Duration.ofMinutes(10));
  }

  @Test
  void theStoreIsTheInMemoryOneConfiguredWithTheProperties() {
    assertThat(store).isInstanceOf(InMemoryEmailVerificationStore.class);
    var now = Instant.now();

    assertThat(store.reserveSend("config-test@example.com", now).isAllowed()).isTrue();
    // 설정의 재발송 간격(60초) 안이라 막힌다
    assertThat(store.reserveSend("config-test@example.com", now.plusSeconds(30)).isAllowed())
        .isFalse();
  }

  @Test
  void signupAndPasswordResetUseDifferentStores() {
    assertThat(resetStore).isInstanceOf(InMemoryEmailVerificationStore.class);
    assertThat(resetStore).isNotSameAs(store);
    var now = Instant.now();

    // 가입 인증에서 보낸 이메일이 재설정의 발송 제한·인증번호·토큰에 영향을 주지 않는다
    store.reserveSend("separate@example.com", now);
    store.saveCode("separate@example.com", "signup-hash", now.plusSeconds(600), 1);
    store.saveToken("signup-token", "separate@example.com", now.plusSeconds(600));

    assertThat(resetStore.reserveSend("separate@example.com", now).isAllowed()).isTrue();
    assertThat(resetStore.confirmCode("separate@example.com", "signup-hash", now.plusSeconds(1), 5))
        .isEqualTo(EmailVerificationStore.ConfirmOutcome.EXPIRED_OR_MISSING);
    assertThat(resetStore.findTokenEmail("signup-token", now)).isEmpty();
  }

  @Test
  void hasherIsAvailable() {
    assertThat(hasher.hashToken("abc")).hasSize(64);
  }
}
