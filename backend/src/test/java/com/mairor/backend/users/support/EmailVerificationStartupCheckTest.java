package com.mairor.backend.users.support;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.common.mail.AppMailProperties;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

/** 인증을 요구하도록 켠 운영 환경에서 설정이 빠졌을 때 시작 단계에서 실패하는지 확인한다. */
class EmailVerificationStartupCheckTest {

  @Configuration
  @EnableConfigurationProperties({
    SignupProperties.class,
    AppMailProperties.class,
    EmailVerificationProperties.class
  })
  static class Config {}

  private final ApplicationContextRunner runner =
      new ApplicationContextRunner()
          .withUserConfiguration(Config.class, EmailVerificationStartupCheck.class)
          .withPropertyValues(
              "app.email-verification.code-ttl=10m",
              "app.email-verification.resend-cooldown=60s",
              "app.email-verification.hourly-limit=5",
              "app.email-verification.max-attempts=5",
              "app.email-verification.token-ttl=30m");

  private ApplicationContextRunner prod() {
    return runner.withInitializer(c -> c.getEnvironment().setActiveProfiles("prod"));
  }

  @Test
  void prodRequiringVerification_withMailDisabled_failsAtStartup() {
    prod()
        .withPropertyValues(
            "app.signup.require-email-verification=true",
            "app.mail.enabled=false",
            "app.email-verification.secret=s3cret")
        .run(
            context ->
                assertThat(context)
                    .hasFailed()
                    .getFailure()
                    .rootCause()
                    .hasMessageContaining("MAIL_ENABLED"));
  }

  @Test
  void prodRequiringVerification_withoutSecret_failsAtStartup() {
    prod()
        .withPropertyValues(
            "app.signup.require-email-verification=true",
            "app.mail.enabled=true",
            "app.email-verification.secret=")
        .run(
            context ->
                assertThat(context)
                    .hasFailed()
                    .getFailure()
                    .rootCause()
                    .hasMessageContaining("EMAIL_VERIFICATION_SECRET"));
  }

  @Test
  void prodRequiringVerification_withMailAndSecret_starts() {
    prod()
        .withPropertyValues(
            "app.signup.require-email-verification=true",
            "app.mail.enabled=true",
            "app.email-verification.secret=s3cret")
        .run(context -> assertThat(context).hasNotFailed());
  }

  @Test
  void prodNotRequiringVerification_startsWithoutAnyMailSetup() {
    prod()
        .withPropertyValues("app.signup.require-email-verification=false", "app.mail.enabled=false")
        .run(context -> assertThat(context).hasNotFailed());
  }

  @Test
  void defaultIsNotRequiringVerification() {
    prod()
        .withPropertyValues("app.mail.enabled=false")
        .run(context -> assertThat(context).hasNotFailed());
  }

  @Test
  void outsideProd_requiringVerificationWithoutMailOrSecret_stillStarts() {
    runner
        .withPropertyValues("app.signup.require-email-verification=true", "app.mail.enabled=false")
        .run(context -> assertThat(context).hasNotFailed());
  }
}
