package com.mairor.backend.users.support;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class GoogleSignupStoreTest {

  private static final Instant NOW = Instant.parse("2026-11-02T00:00:00Z");

  private final GoogleSignupStore store = create(Duration.ofMinutes(10));

  /** 저장소 구현. Redis 구현 테스트가 덮어쓴다. */
  GoogleSignupStore create(Duration ttl) {
    return new GoogleSignupStore(ttl);
  }

  @Test
  void save_setsTheExpiryAfterTtl() {
    assertThat(store.save("key", "sub", "a@gmail.com", "이름", NOW).expiresAt())
        .isEqualTo(NOW.plus(Duration.ofMinutes(10)));
  }

  @Test
  void find_doesNotConsume_butTakeDoes() {
    store.save("key", "sub", "a@gmail.com", null, NOW);

    assertThat(store.find("key", NOW)).isPresent();
    assertThat(store.find("key", NOW)).isPresent();
    assertThat(store.take("key", NOW))
        .get()
        .satisfies(
            p -> {
              assertThat(p.subject()).isEqualTo("sub");
              assertThat(p.email()).isEqualTo("a@gmail.com");
              assertThat(p.name()).isNull();
            });
    assertThat(store.find("key", NOW)).isEmpty();
    assertThat(store.take("key", NOW)).isEmpty();
  }

  @Test
  void expiredPending_isNotFound() {
    store.save("key", "sub", "a@gmail.com", null, NOW);
    Instant expiry = NOW.plus(Duration.ofMinutes(10));

    assertThat(store.find("key", expiry)).isEmpty();
    assertThat(store.take("key", expiry)).isEmpty();
  }

  @Test
  void toStringHidesSubjectAndEmail() {
    assertThat(store.save("key", "secret-sub", "secret@gmail.com", null, NOW).toString())
        .doesNotContain("secret");
  }
}
