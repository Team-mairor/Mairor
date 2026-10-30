package com.mairor.backend.common.security;

import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.error.ErrorResponseWriter;
import java.time.Clock;
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextHolderFilter;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfException;
import org.springframework.security.web.csrf.CsrfFilter;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.security.web.util.matcher.OrRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;
import org.springframework.session.web.http.CookieSerializer;

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

  private static final RequestMatcher LOGIN =
      PathPatternRequestMatcher.withDefaults().matcher(HttpMethod.POST, "/v1/users/login");

  /** 세션·CSRF 토큰 없이 호출하는 공개 POST. 인가·CSRF 제외·Origin 검증이 모두 이 목록을 따른다. */
  private static final List<RequestMatcher> PUBLIC_POSTS =
      List.of(
          SIGN_UP, EMAIL_AVAILABILITY, EMAIL_VERIFICATION_SEND, EMAIL_VERIFICATION_CONFIRM, LOGIN);

  /**
   * 인증 컨텍스트 저장소. 필터 체인과 로그인 컨트롤러가 같은 인스턴스를 쓴다. 컨트롤러는 필터 체인 밖에서 로그인하므로 {@code SecurityContextHolder}
   * 에 넣는 것만으로는 다음 요청에 유지되지 않고, 이 저장소에 명시적으로 저장해야 한다.
   */
  @Bean
  SecurityContextRepository securityContextRepository() {
    return new DelegatingSecurityContextRepository(
        new RequestAttributeSecurityContextRepository(),
        new HttpSessionSecurityContextRepository());
  }

  /**
   * CSRF 토큰 저장소(세션 속성)와 요청 핸들러(마스킹). CSRF 필터와 로그인 처리({@code SessionEstablisher})가 같은 인스턴스를 써서, 로그인이
   * 발급한 토큰을 필터가 그대로 검증한다.
   */
  @Bean
  CsrfTokenRepository csrfTokenRepository() {
    return new HttpSessionCsrfTokenRepository();
  }

  @Bean
  CsrfTokenRequestHandler csrfTokenRequestHandler() {
    return new XorCsrfTokenRequestAttributeHandler();
  }

  private static final RequestMatcher HEALTH =
      new OrRequestMatcher(path("/health"), path("/actuator/health"), path("/actuator/health/**"));

  /** API 문서(Swagger). 운영에서는 springdoc 을 꺼서(application-prod.yml) 404 가 된다. */
  private static final RequestMatcher SWAGGER =
      new OrRequestMatcher(
          path("/swagger-ui/**"), path("/swagger-ui.html"), path("/v3/api-docs/**"));

  /** 인증 없이 열려 있는 경로 전체. 인가 규칙과 {@link SessionLifetimeFilter}(만료된 세션이어도 이 경로는 막지 않는다)가 같은 목록을 쓴다. */
  private static final RequestMatcher PERMIT_ALL =
      new OrRequestMatcher(HEALTH, new OrRequestMatcher(PUBLIC_POSTS), SWAGGER);

  private static RequestMatcher path(String pattern) {
    return PathPatternRequestMatcher.withDefaults().matcher(pattern);
  }

  @Bean
  SecurityFilterChain securityFilterChain(
      HttpSecurity http,
      ErrorResponseWriter errorWriter,
      OriginProperties originProperties,
      SecurityContextRepository securityContextRepository,
      SessionLifetimePolicy sessionLifetimePolicy,
      CsrfTokenRepository csrfTokenRepository,
      CsrfTokenRequestHandler csrfTokenRequestHandler,
      SessionMetrics sessionMetrics,
      SessionEndNotifier sessionEndNotifier,
      Clock clock,
      CookieSerializer cookieSerializer)
      throws Exception {
    http.securityContext(context -> context.securityContextRepository(securityContextRepository))
        // API 서버라 저장된 요청이 필요 없다. 기본값은 미인증 요청마다 익명 세션과 쿠키를 만들어 401 응답마다 세션 행이 쌓인다
        .requestCache(cache -> cache.disable())
        .authorizeHttpRequests(
            auth -> auth.requestMatchers(PERMIT_ALL).permitAll().anyRequest().authenticated())
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
        .csrf(
            csrf ->
                csrf.csrfTokenRepository(csrfTokenRepository)
                    .csrfTokenRequestHandler(csrfTokenRequestHandler)
                    .ignoringRequestMatchers(new OrRequestMatcher(PUBLIC_POSTS)))
        // 필터를 빈으로 노출하면 서블릿 컨테이너에 한 번 더 등록되므로 여기서 만들어 보안 체인에만 끼운다
        .addFilterBefore(
            new OriginCheckFilter(PUBLIC_POSTS, originProperties.allowedOrigins(), errorWriter),
            CsrfFilter.class)
        // 세션을 읽은 뒤(SecurityContextHolderFilter), CSRF 검사 전에 절대 만료를 판단하고 쿠키를 갱신한다
        .addFilterAfter(
            new SessionLifetimeFilter(
                sessionLifetimePolicy, clock, errorWriter, PERMIT_ALL, sessionEndNotifier),
            SecurityContextHolderFilter.class)
        .addFilterAfter(
            new SessionCookieRefreshFilter(
                sessionLifetimePolicy, clock, cookieSerializer, sessionMetrics),
            SessionLifetimeFilter.class)
        .httpBasic(AbstractHttpConfigurer::disable)
        .formLogin(AbstractHttpConfigurer::disable);
    return http.build();
  }
}
