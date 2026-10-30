package com.mairor.backend.users.support;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

/**
 * 인증 정책의 시간 설정이 잘못되면 앱이 시작하지 않는지 확인한다. 가입 이메일 인증({@code app.email-verification})과 비밀번호 재설정({@code
 * app.password-reset})이 같은 규칙을 따른다: 인증번호·토큰 유효 시간은 0보다 길어야 하고(0 이면 만들자마자 만료된다), 재발송 간격은 0 이상이어야
 * 한다(0 은 간격 없음).
 */
class VerificationPropertiesValidationTest {

  @Configuration
  @EnableConfigurationProperties({EmailVerificationProperties.class, PasswordResetProperties.class})
  static class PropertiesConfig {}

  private final ApplicationContextRunner runner =
      new ApplicationContextRunner()
          .withUserConfiguration(PropertiesConfig.class)
          .withPropertyValues(
              "app.email-verification.code-ttl=10m",
              "app.email-verification.resend-cooldown=60s",
              "app.email-verification.hourly-limit=5",
              "app.email-verification.max-attempts=5",
              "app.email-verification.token-ttl=30m",
              "app.password-reset.code-ttl=10m",
              "app.password-reset.resend-cooldown=60s",
              "app.password-reset.hourly-limit=5",
              "app.password-reset.max-attempts=5",
              "app.password-reset.token-ttl=10m");

  private void assertStarts(String... properties) {
    runner.withPropertyValues(properties).run(context -> assertThat(context).hasNotFailed());
  }

  private void assertFailsOn(String property, String value) {
    runner
        .withPropertyValues(property + "=" + value)
        .run(
            context ->
                assertThat(context)
                    .hasFailed()
                    .getFailure()
                    .rootCause()
                    .hasMessageContaining(property.substring(property.lastIndexOf('.') + 1)));
  }

  @Test
  void theDefaultsStart() {
    assertStarts();
  }

  @Test
  void aZeroResendCooldownIsAllowedForBoth() {
    assertStarts(
        "app.email-verification.resend-cooldown=0s", "app.password-reset.resend-cooldown=0s");
  }

  @Test
  void passwordResetRejectsANonPositiveCodeTtl() {
    assertFailsOn("app.password-reset.code-ttl", "0s");
    assertFailsOn("app.password-reset.code-ttl", "-1s");
  }

  @Test
  void passwordResetRejectsANonPositiveTokenTtl() {
    assertFailsOn("app.password-reset.token-ttl", "0s");
    assertFailsOn("app.password-reset.token-ttl", "-1m");
  }

  @Test
  void passwordResetRejectsANegativeResendCooldown() {
    assertFailsOn("app.password-reset.resend-cooldown", "-1s");
  }

  @Test
  void signupVerificationRejectsANonPositiveCodeTtl() {
    assertFailsOn("app.email-verification.code-ttl", "0s");
    assertFailsOn("app.email-verification.code-ttl", "-1s");
  }

  @Test
  void signupVerificationRejectsANonPositiveTokenTtl() {
    assertFailsOn("app.email-verification.token-ttl", "0s");
    assertFailsOn("app.email-verification.token-ttl", "-1m");
  }

  @Test
  void signupVerificationRejectsANegativeResendCooldown() {
    assertFailsOn("app.email-verification.resend-cooldown", "-1s");
  }
}
