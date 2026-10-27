package com.mairor.backend.common.security;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

/** 허용 Origin 설정 바인딩: Spring 컨텍스트 전체를 띄우지 않고 application*.yml 만 읽어 확인한다 (Docker 불필요). */
class OriginPropertiesTest {

  @Configuration
  @EnableConfigurationProperties(OriginProperties.class)
  static class Config {}

  /** 개발자 로컬의 backend/.env 가 결과에 섞이지 않도록 config import 를 막는다. */
  private final ApplicationContextRunner runner =
      new ApplicationContextRunner()
          .withUserConfiguration(Config.class)
          .withInitializer(new ConfigDataApplicationContextInitializer())
          .withPropertyValues("spring.config.import=optional:classpath:/does-not-exist.properties");

  @Test
  void devProfile_defaultsToLocalFrontendAndSwaggerUi() {
    runner
        .withPropertyValues("spring.profiles.active=dev")
        .run(
            context ->
                assertThat(context.getBean(OriginProperties.class).allowedOrigins())
                    .containsExactly(
                        "http://localhost:3000",
                        "https://localhost:3000",
                        "http://localhost:8080"));
  }

  @Test
  void prodProfile_withoutAllowedOrigins_refusesToStart() {
    runner
        .withPropertyValues("spring.profiles.active=prod")
        .run(
            context -> {
              assertThat(context).hasFailed();
              assertThat(context.getStartupFailure())
                  .hasStackTraceContaining("app.security.allowed-origins");
            });
  }

  @Test
  void prodProfile_withExplicitValue_binds() {
    runner
        .withPropertyValues(
            "spring.profiles.active=prod",
            "app.security.allowed-origins=https://mairor.example.com")
        .run(
            context ->
                assertThat(context.getBean(OriginProperties.class).allowedOrigins())
                    .containsExactly("https://mairor.example.com"));
  }

  @Test
  void commaSeparatedValue_isSplitAndTrimmed() {
    runner
        .withPropertyValues(
            "spring.profiles.active=prod",
            "app.security.allowed-origins=https://a.example.com , http://localhost:3000")
        .run(
            context ->
                assertThat(context.getBean(OriginProperties.class).allowedOrigins())
                    .containsExactly("https://a.example.com", "http://localhost:3000"));
  }

  @Test
  void blankValue_refusesToStart() {
    runner
        .withPropertyValues("spring.profiles.active=prod", "app.security.allowed-origins=")
        .run(context -> assertThat(context).hasFailed());
  }
}
