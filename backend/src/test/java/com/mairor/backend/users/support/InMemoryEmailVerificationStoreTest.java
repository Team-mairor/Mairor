package com.mairor.backend.users.support;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class InMemoryEmailVerificationStoreTest extends EmailVerificationStoreContract {

  @Override
  protected EmailVerificationStore create(Duration cooldown, int hourlyLimit) {
    return new InMemoryEmailVerificationStore(cooldown, hourlyLimit);
  }

  @Test
  void aTokenWhoseEmailIndexWasEvictedIsNoLongerValid() {
    var store = new InMemoryEmailVerificationStore(Duration.ofSeconds(60), 5);
    var expiresAt = Instant.parse("2026-10-27T00:10:00Z");
    var now = Instant.parse("2026-10-27T00:00:00Z");
    store.saveToken("token-hash", "member@example.com", expiresAt);

    // 크기 제한 때문에 이메일 쪽 맵만 퇴거된 상황: 해시 쪽에 항목이 남아 있어도 유효로 보지 않는다
    store.forgetEmailIndex("member@example.com");

    assertThat(store.findTokenEmail("token-hash", now)).isEmpty();
    assertThat(store.hasValidToken("token-hash", "member@example.com", now)).isFalse();
  }

  @Test
  void afterTheEmailIndexWasEvictedANewTokenWorksAndOldOperationsDoNotFail() {
    var store = new InMemoryEmailVerificationStore(Duration.ofSeconds(60), 5);
    var expiresAt = Instant.parse("2026-10-27T00:10:00Z");
    var now = Instant.parse("2026-10-27T00:00:00Z");
    store.saveToken("old-hash", "member@example.com", expiresAt);
    store.forgetEmailIndex("member@example.com");

    store.deleteToken("old-hash");
    store.invalidateAll("member@example.com");
    store.saveToken("new-hash", "member@example.com", expiresAt);

    assertThat(store.findTokenEmail("new-hash", now)).contains("member@example.com");
    assertThat(store.findTokenEmail("old-hash", now)).isEmpty();
  }

  @Test
  void rejectsInvalidPolicy() {
    assertThatThrownBy(() -> new InMemoryEmailVerificationStore(Duration.ofSeconds(-1), 5))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new InMemoryEmailVerificationStore(Duration.ofSeconds(60), 0))
        .isInstanceOf(IllegalArgumentException.class);
  }
}
