package com.mairor.backend.testsupport;

import com.mairor.backend.common.security.SessionAttributes;
import com.mairor.backend.users.support.AuthenticatedUser;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.springframework.boot.test.context.TestComponent;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * 인증된 세션을 만들어 주는 테스트 전용 설정. 로그인 API 와 무관하게 세션 동작만 검증할 때 쓴다. 실제 서버 설정을 바꾸지 않고 {@code @Import} 로만
 * 붙인다. 가변 시계({@link MutableClock})를 {@code @Primary} {@link Clock} 으로 등록하므로, 이 설정을 가져온 테스트에서는 필터가 이
 * 시계를 쓴다.
 *
 * <ul>
 *   <li>{@code POST /test-support/login}: 공개 경로. 운영 코드와 같은 {@link SecurityContextRepository} 로
 *       컨텍스트를 저장하고 로그인 시각({@link SessionAttributes#AUTHENTICATED_AT})을 기록한다. {@code userId}·{@code
 *       email} 로 회원을 정하고, {@code omitAuthenticatedAt=true} 면 로그인 시각을 기록하지 않는다.
 *   <li>그 밖의 {@code /test-support/*}: 운영 보안 체인이 보호하는 경로. 응답 종류(본문 있음·204·500)와 세션을 바꾸는 요청(폐기·ID
 *       교체)을 만든다.
 * </ul>
 */
@TestConfiguration(proxyBeanMethods = false)
public class AuthenticatedSessionTestConfig {

  @Bean
  @Primary
  MutableClock mutableClock() {
    return new MutableClock(Instant.now());
  }

  /** 로그인 경로만 인증·CSRF 없이 열어 두는 별도 체인. 운영 체인보다 먼저 맞춘다. */
  @Bean
  @Order(Ordered.HIGHEST_PRECEDENCE)
  SecurityFilterChain testSupportLoginChain(
      HttpSecurity http, SecurityContextRepository securityContextRepository) throws Exception {
    http.securityMatcher(
            PathPatternRequestMatcher.withDefaults()
                .matcher(HttpMethod.POST, "/test-support/login"))
        .authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
        .csrf(AbstractHttpConfigurer::disable)
        .securityContext(context -> context.securityContextRepository(securityContextRepository));
    return http.build();
  }

  /** 익명 세션을 만드는 경로. CSRF 필터는 켜 둔 채 인증만 열어서, 로그인 전 세션에 CSRF 토큰이 들어 있는 상황(예: 로그인 화면을 연 브라우저)을 만든다. */
  @Bean
  @Order(Ordered.HIGHEST_PRECEDENCE)
  SecurityFilterChain testSupportAnonymousChain(
      HttpSecurity http, SecurityContextRepository securityContextRepository) throws Exception {
    http.securityMatcher(
            PathPatternRequestMatcher.withDefaults()
                .matcher(HttpMethod.GET, "/test-support/anonymous-session"))
        .authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
        .securityContext(context -> context.securityContextRepository(securityContextRepository));
    return http.build();
  }

  /**
   * 이 설정을 {@code @Import} 하면 멤버 클래스로 함께 등록된다. {@code @TestComponent} 라서 컴포넌트 스캔에서는 빠지므로, 설정을 가져오지
   * 않은 다른 테스트에는 이 경로가 열리지 않는다.
   */
  @TestComponent
  @RestController
  public static class TestSupportController {

    private final SecurityContextRepository securityContextRepository;
    private final Clock clock;

    TestSupportController(SecurityContextRepository securityContextRepository, Clock clock) {
      this.securityContextRepository = securityContextRepository;
      this.clock = clock;
    }

    /** 응답 본문은 로그인한 회원의 userId. */
    @PostMapping(value = "/test-support/login", produces = "text/plain")
    String login(
        @RequestParam(required = false) UUID userId,
        @RequestParam(defaultValue = "member@example.com") String email,
        @RequestParam(defaultValue = "false") boolean omitAuthenticatedAt,
        HttpServletRequest request,
        HttpServletResponse response) {
      UUID id = userId != null ? userId : UUID.randomUUID();
      Authentication authentication =
          UsernamePasswordAuthenticationToken.authenticated(
              new AuthenticatedUser(id, email),
              null,
              List.of(new SimpleGrantedAuthority("ROLE_USER")));
      SecurityContext context = SecurityContextHolder.createEmptyContext();
      context.setAuthentication(authentication);
      SecurityContextHolder.setContext(context);
      securityContextRepository.saveContext(context, request, response);
      if (!omitAuthenticatedAt) {
        request.getSession().setAttribute(SessionAttributes.AUTHENTICATED_AT, clock.instant());
      }
      return id.toString();
    }

    /** 응답 본문은 이 익명 세션에 저장된 CSRF 토큰(마스킹된 값). 세션 쿠키가 함께 내려간다. */
    @GetMapping(value = "/test-support/anonymous-session", produces = "text/plain")
    String anonymousSession(HttpServletRequest request) {
      CsrfToken token = (CsrfToken) request.getAttribute(CsrfToken.class.getName());
      return token.getToken();
    }

    @GetMapping(value = "/test-support/whoami", produces = "text/plain")
    String whoami(Authentication authentication) {
      return authentication.getName();
    }

    /** 본문 없는 204. 필터 안에서 응답이 커밋되지 않은 채 체인이 반환되는 경로. */
    @GetMapping("/test-support/no-content")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    void noContent() {}

    /** 처리되지 않은 예외로 500 이 나는 요청. */
    @GetMapping("/test-support/error")
    String error() {
      throw new IllegalStateException("테스트용 오류");
    }

    /** CSRF 토큰이 필요한 변경 요청. */
    @PostMapping(value = "/test-support/change", produces = "text/plain")
    String change() {
      return "changed";
    }

    /** 로그아웃처럼 세션을 요청 안에서 폐기한다. 갱신 억제 플래그는 일부러 세우지 않는다. */
    @GetMapping("/test-support/invalidate")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    void invalidate(HttpServletRequest request) {
      SecurityContextHolder.clearContext();
      HttpSession session = request.getSession(false);
      if (session != null) {
        session.invalidate();
      }
    }

    /** 직렬화할 수 없는 값을 세션 속성에 넣는다(서버 버그를 흉내 낸다). 세션을 저장하는 응답 커밋 때 실패한다. */
    @GetMapping("/test-support/unserializable")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    void unserializable(HttpServletRequest request) {
      request.getSession().setAttribute("notSerializable", new Object());
    }

    /** 로그인처럼 요청 안에서 세션 ID 를 교체한다. 갱신 억제 플래그는 일부러 세우지 않는다. */
    @GetMapping(value = "/test-support/rotate", produces = "text/plain")
    String rotate(HttpServletRequest request) {
      return request.changeSessionId();
    }
  }
}
