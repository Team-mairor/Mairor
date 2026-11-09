package com.mairor.backend.common.web;

import io.swagger.v3.oas.annotations.enums.SecuritySchemeIn;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import java.util.List;
import org.springdoc.core.customizers.OperationCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * API 문서의 인증 방식 표기. 인증이 필요한 API 는 {@code @SecurityRequirement} 로 아래 이름을 가리킨다.
 *
 * <p>Swagger UI 로 호출해 볼 때
 *
 * <ol>
 *   <li>{@code POST /v1/users/login} 을 호출한다. 응답의 세션 쿠키는 브라우저가 저장해 이후 요청에 자동으로 실어 보낸다. {@code
 *       Secure} 쿠키라 {@code https} 이거나 {@code localhost} 일 때만 저장된다. 저장되지 않으면 curl 등으로 {@code Cookie}
 *       헤더를 직접 보낸다.
 *   <li>변경 요청(POST·PUT·PATCH·DELETE)에는 {@code csrfToken} 이 필요하다. 로그인·내 계정 조회 응답의 값을 Swagger UI 가
 *       자동으로 실어 보낸다({@link SwaggerCsrfAutofillConfig}). Authorize 의 {@code csrfToken} 칸에 직접 넣으면 그
 *       값을 쓴다.
 * </ol>
 */
@Configuration
@SecurityScheme(
    name = OpenApiConfig.SESSION_COOKIE,
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.COOKIE,
    paramName = "__Host-sessionId",
    description = "로그인 응답이 내려주는 세션 쿠키(HttpOnly·Secure·SameSite=Strict). 브라우저가 자동으로 보내므로 직접 넣지 않는다.")
@SecurityScheme(
    name = OpenApiConfig.CSRF_TOKEN,
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.HEADER,
    paramName = "X-CSRF-TOKEN",
    description =
        "변경 요청(POST·PUT·PATCH·DELETE)에 필요한 값. Swagger UI 에서는 로그인·내 계정 조회 후 자동으로 들어가므로 비워 둔다."
            + " 직접 넣으면 그 값을 쓰며, 로그인할 때마다 새로 발급되므로 가장 최근 응답의 값이어야 한다.")
@SecurityScheme(
    name = OpenApiConfig.INTERNAL_TOKEN,
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.HEADER,
    paramName = "X-Internal-Token",
    description =
        "내부 API(/v1/internal/**) 공유 토큰. 운영자 명령과 AI 서버 콜백이 쓴다. 값은 서버 설정(INTERNAL_API_TOKEN)과 같아야 한다.")
@SecurityScheme(
    name = OpenApiConfig.PROCESSOR_TOKEN,
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.HEADER,
    paramName = "X-Processor-Token",
    description =
        "영상 전처리 노트북 API(/v1/internal/processor/**) 토큰. 운영자 토큰과 다른 값이고 서버 설정(PROCESSOR_API_TOKEN)과 같아야 한다.")
public class OpenApiConfig {

  public static final String INTERNAL_TOKEN = "internalToken";
  public static final String PROCESSOR_TOKEN = "processorToken";

  public static final String SESSION_COOKIE = "sessionCookie";
  public static final String CSRF_TOKEN = "csrfToken";

  /**
   * 한 API 에 {@code @SecurityRequirement} 를 여러 개 붙이면 springdoc 은 "둘 중 하나면 된다"(OR)로 문서를 만든다. 이 프로젝트는
   * 세션 쿠키와 CSRF 토큰을 <b>둘 다</b> 요구하는 API 가 있으므로, 여러 개를 붙인 API 는 모두 필요한 하나의 요구 사항(AND)으로 합친다.
   */
  @Bean
  OperationCustomizer requireAllSecuritySchemes() {
    return (operation, handlerMethod) -> {
      List<SecurityRequirement> requirements = operation.getSecurity();
      if (requirements != null && requirements.size() > 1) {
        SecurityRequirement merged = new SecurityRequirement();
        requirements.forEach(requirement -> requirement.forEach(merged::addList));
        operation.setSecurity(List.of(merged));
      }
      return operation;
    };
  }
}
