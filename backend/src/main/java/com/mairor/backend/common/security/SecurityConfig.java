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
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.NegatedRequestMatcher;
import org.springframework.security.web.util.matcher.OrRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;
import org.springframework.session.web.http.CookieSerializer;

/**
 * 보안 설정. 헬스체크, 공개 변경 요청({@link #PUBLIC_WRITES}), Swagger 만 열고 나머지는 인증을 요구한다. 오류는 공통 형식으로 응답한다: 미인증
 * 401 {@code UNAUTHORIZED}, CSRF 실패 403 {@code CSRF_INVALID}, 그 밖의 권한 실패 403 {@code FORBIDDEN}.
 *
 * <p>CSRF 필터가 인가보다 먼저 돌아 세션 없는 변경 요청은 401이 아니라 403 {@code CSRF_INVALID}가 된다. 공개 변경 요청은 CSRF 검사를 빼고
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

  private static final RequestMatcher PASSWORD_RESET_SEND =
      PathPatternRequestMatcher.withDefaults().matcher(HttpMethod.POST, "/v1/users/password-reset");

  private static final RequestMatcher PASSWORD_RESET_VERIFY =
      PathPatternRequestMatcher.withDefaults()
          .matcher(HttpMethod.POST, "/v1/users/password-reset/verification");

  private static final RequestMatcher PASSWORD_RESET_SAVE =
      PathPatternRequestMatcher.withDefaults()
          .matcher(HttpMethod.PUT, "/v1/users/password-reset/password");

  private static final RequestMatcher GOOGLE_SIGN_UP =
      PathPatternRequestMatcher.withDefaults()
          .matcher(HttpMethod.POST, "/v1/users/oauth/google/signup");

  private static final RequestMatcher PUBLIC_PHOTO_SHARE =
      PathPatternRequestMatcher.withDefaults()
          .matcher(HttpMethod.GET, "/v1/photo-shares/{shareId}");

  private static final RequestMatcher CREATE_PHOTO_SHARE =
      PathPatternRequestMatcher.withDefaults().matcher(HttpMethod.POST, "/v1/photo-shares");

  /**
   * 세션·CSRF 토큰 없이 호출하는 공개 변경 요청(POST, 비밀번호 재설정 저장만 PUT). 인가·CSRF 제외·Origin 검증이 모두 이 목록을 따른다. 로그인한
   * 세션 쿠키가 함께 와도 CSRF 검사를 하지 않는다. 대신 허용 Origin 검증을 받는다.
   */
  private static final List<RequestMatcher> PUBLIC_WRITES =
      List.of(
          SIGN_UP,
          EMAIL_AVAILABILITY,
          EMAIL_VERIFICATION_SEND,
          EMAIL_VERIFICATION_CONFIRM,
          LOGIN,
          PASSWORD_RESET_SEND,
          PASSWORD_RESET_VERIFY,
          PASSWORD_RESET_SAVE,
          GOOGLE_SIGN_UP,
          CREATE_PHOTO_SHARE);

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

  /**
   * Google 로그인 시작·callback·가입 대기 조회. 모두 GET 이라 CSRF 와 Origin 검증 대상이 아니다. 시작·callback 은
   * state·nonce·PKCE 와 인가 요청 쿠키로, 가입 대기 조회는 HttpOnly 가입 대기 쿠키로 보호한다.
   */
  private static final RequestMatcher GOOGLE_LOGIN =
      new OrRequestMatcher(
          PathPatternRequestMatcher.withDefaults()
              .matcher(HttpMethod.GET, "/v1/users/oauth/google"),
          PathPatternRequestMatcher.withDefaults()
              .matcher(HttpMethod.GET, "/v1/users/oauth/google/callback"),
          PathPatternRequestMatcher.withDefaults()
              .matcher(HttpMethod.GET, "/v1/users/oauth/google/signup"));

  /**
   * 내부 API(서버끼리 부르는 API · AI 콜백). 세션·CSRF 대신 {@link InternalTokenFilter}가 공유 토큰 헤더로 지킨다. 인가 규칙에서는
   * 공개로 두고 토큰 필터가 막는다.
   */
  static final RequestMatcher INTERNAL =
      PathPatternRequestMatcher.withDefaults().matcher("/v1/internal/**");

  /**
   * AI 서버 콜백. AI 는 인증 헤더를 붙이지 못해 공유 토큰 검사에서 뺀다. 대신 nginx 가 바깥에서 이 경로를 막고({@code
   * frontend/nginx/api.conf}), AI 는 내부망으로 api 에 바로 붙는다.
   */
  static final RequestMatcher AI_CALLBACK =
      PathPatternRequestMatcher.withDefaults().matcher("/v1/internal/ai/**");

  /**
   * 영상 전처리 노트북 API(S15P31A306-357). 노트북은 인터넷에서 부르므로 공유 토큰과 다른 토큰({@code X-Processor-Token})으로 지킨다.
   */
  static final RequestMatcher PROCESSOR =
      PathPatternRequestMatcher.withDefaults().matcher("/v1/internal/processor/**");

  /** 공유 토큰을 요구하는 내부 API(카탈로그 적재 등). */
  static final RequestMatcher INTERNAL_TOKEN_REQUIRED =
      new AndRequestMatcher(
          INTERNAL, new NegatedRequestMatcher(AI_CALLBACK), new NegatedRequestMatcher(PROCESSOR));

  /** 인증 없이 열려 있는 경로 전체. 인가 규칙과 {@link SessionLifetimeFilter}(만료된 세션이어도 이 경로는 막지 않는다)가 같은 목록을 쓴다. */
  private static final RequestMatcher PERMIT_ALL =
      new OrRequestMatcher(
          HEALTH,
          new OrRequestMatcher(PUBLIC_WRITES),
          GOOGLE_LOGIN,
          PUBLIC_PHOTO_SHARE,
          SWAGGER,
          INTERNAL);

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
      CookieSerializer cookieSerializer,
      InternalApiProperties internalApiProperties,
      ProcessorApiProperties processorApiProperties)
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
                    .ignoringRequestMatchers(new OrRequestMatcher(PUBLIC_WRITES), INTERNAL))
        // 필터를 빈으로 노출하면 서블릿 컨테이너에 한 번 더 등록되므로 여기서 만들어 보안 체인에만 끼운다
        .addFilterBefore(
            new OriginCheckFilter(PUBLIC_WRITES, originProperties.allowedOrigins(), errorWriter),
            CsrfFilter.class)
        // 내부 API 는 CSRF 대신 공유 토큰으로 막는다. 세션을 읽기 전에 거절한다
        .addFilterBefore(
            new InternalTokenFilter(INTERNAL_TOKEN_REQUIRED, internalApiProperties, errorWriter),
            SecurityContextHolderFilter.class)
        .addFilterBefore(
            new InternalTokenFilter(PROCESSOR, processorApiProperties, errorWriter),
            SecurityContextHolderFilter.class)
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
