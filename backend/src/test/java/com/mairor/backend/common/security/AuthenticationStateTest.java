package com.mairor.backend.common.security;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

class AuthenticationStateTest {

  @Test
  void aMissingAuthenticationIsNotAuthenticated() {
    assertThat(AuthenticationState.isAuthenticated(null)).isFalse();
  }

  @Test
  void anAnonymousAuthenticationIsNotAuthenticated() {
    var anonymous =
        new AnonymousAuthenticationToken(
            "key", "anonymousUser", List.of(new SimpleGrantedAuthority("ROLE_ANONYMOUS")));

    assertThat(anonymous.isAuthenticated()).isTrue();
    assertThat(AuthenticationState.isAuthenticated(anonymous)).isFalse();
  }

  @Test
  void anUnauthenticatedTokenIsNotAuthenticated() {
    var pending = UsernamePasswordAuthenticationToken.unauthenticated("user", "secret");

    assertThat(AuthenticationState.isAuthenticated(pending)).isFalse();
  }

  @Test
  void anAuthenticatedTokenIsAuthenticated() {
    var member =
        UsernamePasswordAuthenticationToken.authenticated(
            "user", null, List.of(new SimpleGrantedAuthority("ROLE_USER")));

    assertThat(AuthenticationState.isAuthenticated(member)).isTrue();
  }
}
