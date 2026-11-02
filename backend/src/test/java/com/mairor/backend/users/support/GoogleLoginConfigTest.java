package com.mairor.backend.users.support;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.common.error.BusinessException;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;

/** 설정 값에 따라 Google 클라이언트를 등록하거나, 끄거나, 기동을 막는지 확인한다. */
class GoogleLoginConfigTest {

  @Configuration
  @EnableConfigurationProperties(GoogleLoginProperties.class)
  static class Config {}

  private final ApplicationContextRunner runner =
      new ApplicationContextRunner()
          .withUserConfiguration(Config.class, GoogleLoginConfig.class)
          .withPropertyValues(
              "app.oauth.google.authorization-ttl=10m", "app.oauth.google.signup-ttl=10m");

  private static final String[] FULL = {
    "app.oauth.google.client-id=test-client",
    "app.oauth.google.client-secret=test-secret",
    "app.oauth.google.redirect-uri=http://localhost:3000/api/v1/users/oauth/google/callback"
  };

  private ApplicationContextRunner prod() {
    return runner.withInitializer(c -> c.getEnvironment().setActiveProfiles("prod"));
  }

  @Test
  void fullyConfigured_registersGoogleWithOpenIdAndPkce() {
    runner
        .withPropertyValues(FULL)
        .run(
            context -> {
              GoogleClientRegistrations registrations =
                  context.getBean(GoogleClientRegistrations.class);
              assertThat(registrations.available()).isTrue();
              ClientRegistration google = registrations.require();
              assertThat(google.getRegistrationId()).isEqualTo("google");
              assertThat(google.getClientId()).isEqualTo("test-client");
              assertThat(google.getRedirectUri())
                  .isEqualTo("http://localhost:3000/api/v1/users/oauth/google/callback");
              assertThat(google.getAuthorizationGrantType())
                  .isEqualTo(AuthorizationGrantType.AUTHORIZATION_CODE);
              assertThat(google.getScopes()).contains("openid", "email", "profile");
              assertThat(google.getProviderDetails().getIssuerUri())
                  .isEqualTo("https://accounts.google.com");
              assertThat(google.getClientSettings().isRequireProofKey()).isTrue();
            });
  }

  @Test
  void notConfiguredOutsideProd_startsWithGoogleUnavailable() {
    runner.run(
        context -> {
          GoogleClientRegistrations registrations =
              context.getBean(GoogleClientRegistrations.class);
          assertThat(registrations.available()).isFalse();
          assertThatThrownBy(registrations::require)
              .isInstanceOfSatisfying(
                  BusinessException.class,
                  e -> {
                    assertThat(e.status()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
                    assertThat(e.code()).isEqualTo("USERS_GOOGLE_AUTH_UNAVAILABLE");
                  });
        });
  }

  @Test
  void notConfiguredInProd_failsAtStartup() {
    prod()
        .run(
            context ->
                assertThat(context)
                    .hasFailed()
                    .getFailure()
                    .rootCause()
                    .hasMessageContaining("GOOGLE_CLIENT_ID"));
  }

  @Test
  void fullyConfiguredInProd_starts() {
    prod().withPropertyValues(FULL).run(context -> assertThat(context).hasNotFailed());
  }

  @Test
  void partiallyConfigured_failsAtStartup() {
    runner
        .withPropertyValues("app.oauth.google.client-id=test-client")
        .run(
            context ->
                assertThat(context)
                    .hasFailed()
                    .getFailure()
                    .rootCause()
                    .hasMessageContaining("일부만"));
  }

  @Test
  void nonPositiveTtl_failsAtStartup() {
    runner
        .withPropertyValues("app.oauth.google.signup-ttl=0s")
        .run(context -> assertThat(context).hasFailed());
  }

  @Test
  void toStringMasksSecret() {
    runner
        .withPropertyValues(FULL)
        .run(
            context ->
                assertThat(context.getBean(GoogleLoginProperties.class).toString())
                    .doesNotContain("test-secret")
                    .contains("****"));
  }
}
