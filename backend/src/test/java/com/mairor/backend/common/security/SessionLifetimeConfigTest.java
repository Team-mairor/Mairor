package com.mairor.backend.common.security;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

/** 흩어진 세 설정을 모아 정책을 만들고, 관계가 어긋나거나 빠져 있으면 앱이 기동하지 않는지 확인한다. */
class SessionLifetimeConfigTest {

  @Configuration
  @EnableConfigurationProperties(SessionLifetimeProperties.class)
  static class PropertiesConfig {}

  private final ApplicationContextRunner runner =
      new ApplicationContextRunner()
          .withUserConfiguration(PropertiesConfig.class, SessionLifetimeConfig.class)
          .withPropertyValues(
              "spring.session.timeout=3d",
              "server.servlet.session.cookie.max-age=3d",
              "app.session.absolute-timeout=30d");

  @Test
  void collectsThePolicyFromTheThreeSettings() {
    runner.run(
        context -> {
          SessionLifetimePolicy policy = context.getBean(SessionLifetimePolicy.class);
          assertThat(policy.idleTimeout()).isEqualTo(Duration.ofDays(3));
          assertThat(policy.cookieMaxAge()).isEqualTo(Duration.ofDays(3));
          assertThat(policy.absoluteTimeout()).isEqualTo(Duration.ofDays(30));
        });
  }

  @Test
  void failsToStartWhenTheCookieOutlivesTheServerSession() {
    runner
        .withPropertyValues("server.servlet.session.cookie.max-age=4d")
        .run(context -> assertThat(context).hasFailed());
  }

  @Test
  void failsToStartWhenTheIdleTimeoutExceedsTheAbsoluteTimeout() {
    runner
        .withPropertyValues(
            "spring.session.timeout=40d", "server.servlet.session.cookie.max-age=3d")
        .run(context -> assertThat(context).hasFailed());
  }

  @Test
  void failsToStartWhenTheAbsoluteTimeoutIsMissing() {
    new ApplicationContextRunner()
        .withUserConfiguration(PropertiesConfig.class, SessionLifetimeConfig.class)
        .withPropertyValues("spring.session.timeout=3d", "server.servlet.session.cookie.max-age=3d")
        .run(context -> assertThat(context).hasFailed());
  }

  @Test
  void failsToStartWhenTheIdleTimeoutIsMissing() {
    new ApplicationContextRunner()
        .withUserConfiguration(PropertiesConfig.class, SessionLifetimeConfig.class)
        .withPropertyValues(
            "server.servlet.session.cookie.max-age=3d", "app.session.absolute-timeout=30d")
        .run(context -> assertThat(context).hasFailed());
  }

  @Test
  void failsToStartWhenTheCookieMaxAgeIsMissing() {
    new ApplicationContextRunner()
        .withUserConfiguration(PropertiesConfig.class, SessionLifetimeConfig.class)
        .withPropertyValues("spring.session.timeout=3d", "app.session.absolute-timeout=30d")
        .run(context -> assertThat(context).hasFailed());
  }
}
