package com.mairor.backend.common.web;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

/**
 * 운영 설정 파일({@code application-prod.yml})에 API 문서를 끄는 값이 실제로 들어 있는지 확인한다.
 *
 * <p>앱 전체를 띄우지 않고 설정 파일만 읽는다 (Docker·DB 불필요). prod 로 앱을 띄우는 방식은 DB 스키마와 필수 환경변수에 묶여 Swagger 와 무관한
 * 이유로 깨질 수 있어 쓰지 않는다. 끄는 스위치의 동작은 {@link OpenApiDocsDisabledTest} 가 확인한다.
 */
class OpenApiProdConfigTest {

  /** 개발자 로컬의 backend/.env 가 결과에 섞이지 않도록 config import 를 막는다. */
  private final ApplicationContextRunner runner =
      new ApplicationContextRunner()
          .withInitializer(new ConfigDataApplicationContextInitializer())
          .withPropertyValues("spring.config.import=optional:classpath:/does-not-exist.properties");

  @Test
  void prodProfile_disablesApiDocsAndSwaggerUi() {
    runner
        .withPropertyValues("spring.profiles.active=prod")
        .run(
            context -> {
              assertThat(context.getEnvironment().getProperty("springdoc.api-docs.enabled"))
                  .isEqualTo("false");
              assertThat(context.getEnvironment().getProperty("springdoc.swagger-ui.enabled"))
                  .isEqualTo("false");
            });
  }

  @Test
  void devProfile_doesNotDisableThem() {
    runner
        .withPropertyValues("spring.profiles.active=dev")
        .run(
            context -> {
              assertThat(context.getEnvironment().getProperty("springdoc.api-docs.enabled"))
                  .isNotEqualTo("false");
              assertThat(context.getEnvironment().getProperty("springdoc.swagger-ui.enabled"))
                  .isNotEqualTo("false");
            });
  }
}
