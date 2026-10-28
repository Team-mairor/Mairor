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
import org.springframework.security.web.util.matcher.OrRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

/**
 * 보안 설정. 헬스체크, 공개 POST({@link #PUBLIC_POSTS}), Swagger 만 열고 나머지는 인증을 요구한다. 오류는 공통 형식으로 응답한다: 미인증
 * 401 {@code UNAUTHORIZED}, CSRF 실패 403 {@code CSRF_INVALID}, 그 밖의 권한 실패 403 {@code FORBIDDEN}.
 *
 * <p>CSRF 필터가 인가보다 먼저 돌아 세션 없는 변경 요청은 401이 아니라 403 {@code CSRF_INVALID}가 된다. 공개 POST 는 CSRF 검사를 빼고
 * 허용 Origin 검증({@link OriginCheckFilter})으로 보호한다.
 */
@Configuration
@EnableWebSecurity
public class SecurityConfig {

  private static final RequestMatcher SIGN_UP =
      PathPatternRequestMatcher.withDefaults().matcher(HttpMethod.POST, "/v1/users/signup");

  private static final RequestMatcher EMAIL_AVAILABILITY =
      PathPatternRequestMatcher.withDefaults()
          .matcher(HttpMethod.POST, "/v1/users/email-availability");

  private static final RequestMatcher EMAIL_VERIFICATION_SEND =
      PathPatternRequestMatcher.withDefaults()
          .matcher(HttpMethod.POST, "/v1/users/email-verification");

  private static final RequestMatcher EMAIL_VERIFICATION_CONFIRM =
      PathPatternRequestMatcher.withDefaults()
          .matcher(HttpMethod.POST, "/v1/users/email-verification/verification");

  /** 세션·CSRF 토큰 없이 호출하는 공개 POST. 인가·CSRF 제외·Origin 검증이 모두 이 목록을 따른다. */
  private static final List<RequestMatcher> PUBLIC_POSTS =
      List.of(SIGN_UP, EMAIL_AVAILABILITY, EMAIL_VERIFICATION_SEND, EMAIL_VERIFICATION_CONFIRM);

  @Bean
  SecurityFilterChain securityFilterChain(
      HttpSecurity http, ErrorResponseWriter errorWriter, OriginProperties originProperties)
      throws Exception {
    http.authorizeHttpRequests(
            auth ->
                auth.requestMatchers("/health", "/actuator/health", "/actuator/health/**")
                    .permitAll()
                    .requestMatchers(PUBLIC_POSTS.toArray(RequestMatcher[]::new))
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
        .csrf(csrf -> csrf.ignoringRequestMatchers(new OrRequestMatcher(PUBLIC_POSTS)))
        // 필터를 빈으로 노출하면 서블릿 컨테이너에 한 번 더 등록되므로 여기서 만들어 보안 체인에만 끼운다
        .addFilterBefore(
            new OriginCheckFilter(PUBLIC_POSTS, originProperties.allowedOrigins(), errorWriter),
            CsrfFilter.class)
        .httpBasic(AbstractHttpConfigurer::disable)
        .formLogin(AbstractHttpConfigurer::disable);
    return http.build();
  }
}
