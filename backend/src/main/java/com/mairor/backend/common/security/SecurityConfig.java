package com.mairor.backend.common.security;

import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.error.ErrorResponseWriter;
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfException;
import org.springframework.security.web.csrf.CsrfFilter;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

/**
 * 보안 설정. 헬스체크, 회원가입, API 문서(Swagger)만 열고 나머지는 인증을 요구한다. 미인증은 401 {@code UNAUTHORIZED}, CSRF 실패는 403
 * {@code CSRF_INVALID}, 그 밖의 권한 실패는 403 {@code FORBIDDEN}을 공통 오류 형식(JSON)으로 응답한다.
 *
 * <p>CSRF 필터가 인가 검사보다 먼저 돌기 때문에, 세션이 없는 변경 요청도 토큰이 없으면 401이 아니라 403 {@code CSRF_INVALID}가 나간다(노션
 * API 명세 공통 오류 코드).
 *
 * <p>회원가입({@code POST /v1/users})은 세션이 없는 비회원 요청이라 이 경로만 CSRF 토큰 검사에서 빼고, 대신 허용 Origin 검증({@link
 * OriginCheckFilter})으로 보호한다 (공통 규약). 로그인 경로는 로그인 이슈에서 {@link #ORIGIN_PROTECTED}에 한 줄 더하면 된다.
 *
 * <p>세션 로그인·CSRF 토큰 전달은 회원 이슈(로그인)에서 이 설정에 덧붙인다.
 */
@Configuration
@EnableWebSecurity
public class SecurityConfig {

  private static final RequestMatcher SIGN_UP =
      PathPatternRequestMatcher.withDefaults().matcher(HttpMethod.POST, "/v1/users");

  /** 세션·CSRF 토큰 없이 호출되어 허용 Origin 검증이 필요한 요청. */
  private static final List<RequestMatcher> ORIGIN_PROTECTED = List.of(SIGN_UP);

  @Bean
  SecurityFilterChain securityFilterChain(
      HttpSecurity http, ErrorResponseWriter errorWriter, OriginProperties originProperties)
      throws Exception {
    http.authorizeHttpRequests(
            auth ->
                auth.requestMatchers("/health", "/actuator/health", "/actuator/health/**")
                    .permitAll()
                    .requestMatchers(SIGN_UP)
                    .permitAll()
                    // API 문서(Swagger). 운영에서는 springdoc 을 꺼서(application-prod.yml) 404 가 된다
                    .requestMatchers("/swagger-ui/**", "/swagger-ui.html", "/v3/api-docs/**")
                    .permitAll()
                    .anyRequest()
                    .authenticated())
        .exceptionHandling(
            ex ->
                ex.authenticationEntryPoint(
                        (request, response, e) ->
                            errorWriter.write(response, ErrorCode.UNAUTHORIZED))
                    .accessDeniedHandler(
                        (request, response, e) ->
                            errorWriter.write(
                                response,
                                e instanceof CsrfException
                                    ? ErrorCode.CSRF_INVALID
                                    : ErrorCode.FORBIDDEN)))
        .csrf(csrf -> csrf.ignoringRequestMatchers(SIGN_UP))
        // 필터를 빈으로 노출하면 서블릿 컨테이너에 한 번 더 등록되므로 여기서 만들어 보안 체인에만 끼운다
        .addFilterBefore(
            new OriginCheckFilter(ORIGIN_PROTECTED, originProperties.allowedOrigins(), errorWriter),
            CsrfFilter.class)
        .httpBasic(AbstractHttpConfigurer::disable)
        .formLogin(AbstractHttpConfigurer::disable);
    return http.build();
  }
}
