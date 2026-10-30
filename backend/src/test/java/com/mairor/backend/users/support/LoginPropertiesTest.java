package com.mairor.backend.users.support;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

/** {@code app.login.*} 바인딩과 검증. 잘못된 값이면 앱이 기동하지 않아야 한다. */
class LoginPropertiesTest {

  @Configuration
  @EnableConfigurationProperties(LoginProperties.class)
  static class PropertiesConfig {}

  private final ApplicationContextRunner runner =
      new ApplicationContextRunner()
          .withUserConfiguration(PropertiesConfig.class)
          .withPropertyValues(
              "app.login.max-failures=3",
              "app.login.lock-duration=30s",
              "app.login.attempt-ttl=15m",
              "app.login.max-entries=10000",
              "app.login.max-concurrent-hashes=4");

  @Test
  void bindsValidValues() {
    runner.run(
        context -> {
          LoginProperties properties = context.getBean(LoginProperties.class);
          assertThat(properties.maxFailures()).isEqualTo(3);
          assertThat(properties.lockDuration()).isEqualTo(Duration.ofSeconds(30));
          assertThat(properties.attemptTtl()).isEqualTo(Duration.ofMinutes(15));
          assertThat(properties.maxEntries()).isEqualTo(10_000);
          assertThat(properties.maxConcurrentHashes()).isEqualTo(4);
        });
  }

  @Test
  void failsToStartWhenMaxFailuresIsNotPositive() {
    runner
        .withPropertyValues("app.login.max-failures=0")
        .run(context -> assertThat(context).hasFailed());
  }

  @Test
  void failsToStartWhenMaxEntriesIsNotPositive() {
    runner
        .withPropertyValues("app.login.max-entries=0")
        .run(context -> assertThat(context).hasFailed());
  }

  @Test
  void failsToStartWhenMaxConcurrentHashesIsNotPositive() {
    runner
        .withPropertyValues("app.login.max-concurrent-hashes=0")
        .run(context -> assertThat(context).hasFailed());
  }

  @Test
  void failsToStartWhenALockDurationIsZeroOrNegative() {
    runner
        .withPropertyValues("app.login.lock-duration=0s")
        .run(context -> assertThat(context).hasFailed());
    runner
        .withPropertyValues("app.login.lock-duration=-5s")
        .run(context -> assertThat(context).hasFailed());
  }

  @Test
  void failsToStartWhenTheAttemptTtlIsZeroOrNegative() {
    runner
        .withPropertyValues("app.login.attempt-ttl=0s")
        .run(context -> assertThat(context).hasFailed());
  }
}
