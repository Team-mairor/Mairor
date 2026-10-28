package com.mairor.backend.users.support;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Duration;
import org.junit.jupiter.api.Test;

class InMemoryEmailVerificationStoreTest extends EmailVerificationStoreContract {

  @Override
  protected EmailVerificationStore create(Duration cooldown, int hourlyLimit) {
    return new InMemoryEmailVerificationStore(cooldown, hourlyLimit);
  }

  @Test
  void rejectsInvalidPolicy() {
    assertThatThrownBy(() -> new InMemoryEmailVerificationStore(Duration.ofSeconds(-1), 5))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> new InMemoryEmailVerificationStore(Duration.ofSeconds(60), 0))
        .isInstanceOf(IllegalArgumentException.class);
  }
}
