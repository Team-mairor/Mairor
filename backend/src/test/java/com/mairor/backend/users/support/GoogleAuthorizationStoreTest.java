package com.mairor.backend.users.support;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

class GoogleAuthorizationStoreTest {

  private static final Instant NOW = Instant.parse("2026-11-02T00:00:00Z");

  private final GoogleAuthorizationStore store =
      new GoogleAuthorizationStore(Duration.ofMinutes(10));

  private static OAuth2AuthorizationRequest request(String state) {
    return OAuth2AuthorizationRequest.authorizationCode()
        .authorizationUri("https://accounts.google.com/o/oauth2/v2/auth")
        .clientId("test-client")
        .redirectUri("http://localhost:3000/api/v1/users/oauth/google/callback")
        .state(state)
        .build();
  }

  @Test
  void save_returnsExpiryAfterTtl() {
    assertThat(store.save("key", request("s"), NOW)).isEqualTo(NOW.plus(Duration.ofMinutes(10)));
  }

  @Test
  void take_returnsTheSavedRequestOnlyOnce() {
    store.save("key", request("state-1"), NOW);

    assertThat(store.take("key", NOW.plusSeconds(1)))
        .get()
        .extracting(OAuth2AuthorizationRequest::getState)
        .isEqualTo("state-1");
    assertThat(store.take("key", NOW.plusSeconds(2))).isEmpty();
  }

  @Test
  void take_isEmptyAtOrAfterExpiry() {
    store.save("key", request("s"), NOW);

    assertThat(store.take("key", NOW.plus(Duration.ofMinutes(10)))).isEmpty();
  }

  @Test
  void take_isEmptyForUnknownKey() {
    assertThat(store.take("unknown", NOW)).isEmpty();
  }
}
