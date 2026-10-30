package com.mairor.backend.common.web;

import jakarta.servlet.http.HttpServletRequest;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import org.springdoc.core.properties.SwaggerUiConfigProperties;
import org.springdoc.core.properties.SwaggerUiOAuthProperties;
import org.springdoc.core.providers.ObjectMapperProvider;
import org.springdoc.webmvc.ui.SwaggerIndexPageTransformer;
import org.springdoc.webmvc.ui.SwaggerIndexTransformer;
import org.springdoc.webmvc.ui.SwaggerWelcomeCommon;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.web.servlet.resource.ResourceTransformerChain;
import org.springframework.web.servlet.resource.TransformedResource;

/**
 * Swagger UI 에서 로그인 응답의 {@code csrfToken} 을 변경 요청에 자동으로 실어 보내게 한다. springdoc 이 만드는 {@code
 * swagger-initializer.js} 뒤에 {@code swagger/csrf-autofill.js} 를 덧붙인다. Authorize 에 직접 넣은 값이 있으면 그 값을
 * 쓴다. Swagger 가 꺼진 환경(prod)에서는 만들어지지 않는다.
 */
@Configuration
@ConditionalOnProperty(
    prefix = "springdoc.swagger-ui",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true)
public class SwaggerCsrfAutofillConfig {

  static final String INITIALIZER = "swagger-initializer.js";
  static final String SCRIPT_PATH = "swagger/csrf-autofill.js";

  @Bean
  SwaggerIndexTransformer csrfAutofillIndexTransformer(
      SwaggerUiConfigProperties uiConfig,
      SwaggerUiOAuthProperties oauth,
      SwaggerWelcomeCommon welcome,
      ObjectMapperProvider objectMapperProvider) {
    String script = loadScript();
    return new SwaggerIndexPageTransformer(uiConfig, oauth, welcome, objectMapperProvider) {
      @Override
      public Resource transform(
          HttpServletRequest request, Resource resource, ResourceTransformerChain chain)
          throws IOException {
        Resource transformed = super.transform(request, resource, chain);
        if (!INITIALIZER.equals(resource.getFilename())) {
          return transformed;
        }
        String source =
            new String(transformed.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
        return new TransformedResource(
            resource, (source + script).getBytes(StandardCharsets.UTF_8));
      }
    };
  }

  private static String loadScript() {
    try {
      return new String(
          new ClassPathResource(SCRIPT_PATH).getInputStream().readAllBytes(),
          StandardCharsets.UTF_8);
    } catch (IOException e) {
      throw new UncheckedIOException("Swagger CSRF 스크립트를 읽을 수 없습니다: " + SCRIPT_PATH, e);
    }
  }
}
