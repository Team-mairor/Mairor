package com.mairor.backend.users.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.ratelimit.RateLimiter;
import com.mairor.backend.users.dto.response.GoogleSignupPendingResponse;
import com.mairor.backend.users.entity.AuthProvider;
import com.mairor.backend.users.entity.UserIdentity;
import com.mairor.backend.users.repository.UserIdentityRepository;
import com.mairor.backend.users.repository.UserRepository;
import com.mairor.backend.users.support.EmailNormalizer;
import com.mairor.backend.users.support.GoogleAuthFailure;
import com.mairor.backend.users.support.GoogleAuthorizationStore;
import com.mairor.backend.users.support.GoogleClientRegistrations;
import com.mairor.backend.users.support.GoogleOidcAuthenticator;
import com.mairor.backend.users.support.GoogleSignupStore;
import com.mairor.backend.users.support.VerificationHasher;
import com.mairor.backend.users.support.VerificationTokens;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseCookie;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;

/**
 * Google 로그인 (API-USERS-006 시작, API-USERS-007 callback, 가입 대기 조회). 인가 요청(state·nonce·PKCE
 * verifier)은 Spring 의 resolver 로 만들고, 세션이 아닌 서버 저장소에 두며 브라우저에는 그 열쇠만 임시 쿠키로 준다. 로그인 시작만으로는 회원·세션을
 * 만들지 않는다.
 *
 * <p>callback 은 결과와 상관없이 화면 경로로 보낸다. 성공은 서비스 메인({@code /}), 실패는 로그인 화면({@code /login?error=<코드>})
 * 이고 코드는 {@link GoogleAuthFailure} 만 쓴다. Google 이 보낸 오류 문구·code·토큰은 URL·로그에 남기지 않는다.
 */
@Service
public class GoogleLoginService {

  /** 인가 요청 열쇠 쿠키. 세션 쿠키와 달리 {@code SameSite=Lax} 라 Google 에서 돌아오는 최상위 GET 에도 붙는다. */
  public static final String AUTHORIZATION_COOKIE = "__Host-googleAuth";

  /** 처음 온 사용자의 가입 대기 쿠키. 가입 대기 조회·가입 완료가 이 쿠키로 대기를 찾는다. */
  public static final String SIGNUP_COOKIE = "__Host-googleSignup";

  static final String RATE_LIMITED_CODE = "USERS_LOGIN_RATE_LIMITED";
  static final String SIGNUP_EXPIRED_CODE = "USERS_GOOGLE_SIGNUP_EXPIRED";

  static final String SIGNED_IN_LOCATION = "/";
  static final String LOGIN_LOCATION = "/login";
  static final String SIGNUP_LOCATION = "/signup/google";

  /** 사용자가 Google 화면에서 취소했을 때 Google 이 보내는 {@code error} 값. */
  private static final String ACCESS_DENIED = "access_denied";

  private static final Logger log = LoggerFactory.getLogger(GoogleLoginService.class);

  private final GoogleClientRegistrations registrations;
  private final GoogleAuthorizationStore authorizationStore;
  private final GoogleSignupStore signupStore;
  private final GoogleOidcAuthenticator authenticator;
  private final UserIdentityRepository identityRepository;
  private final UserRepository userRepository;
  private final SessionEstablisher sessionEstablisher;
  private final RateLimiter startRateLimiter;
  private final VerificationTokens tokens;
  private final VerificationHasher hasher;
  private final Clock clock;

  public GoogleLoginService(
      GoogleClientRegistrations registrations,
      GoogleAuthorizationStore authorizationStore,
      GoogleSignupStore signupStore,
      GoogleOidcAuthenticator authenticator,
      UserIdentityRepository identityRepository,
      UserRepository userRepository,
      SessionEstablisher sessionEstablisher,
      @Qualifier("googleLoginRateLimiter") RateLimiter startRateLimiter,
      VerificationTokens tokens,
      VerificationHasher hasher,
      Clock clock) {
    this.registrations = registrations;
    this.authorizationStore = authorizationStore;
    this.signupStore = signupStore;
    this.authenticator = authenticator;
    this.identityRepository = identityRepository;
    this.userRepository = userRepository;
    this.sessionEstablisher = sessionEstablisher;
    this.startRateLimiter = startRateLimiter;
    this.tokens = tokens;
    this.hasher = hasher;
    this.clock = clock;
  }

  /**
   * 로그인 시작 결과.
   *
   * @param authorizationUri 브라우저를 보낼 Google 인증 주소
   * @param cookie 인가 요청 열쇠 쿠키
   */
  public record Start(String authorizationUri, ResponseCookie cookie) {}

  /** 인가 요청을 만들어 보관하고 Google 로 보낼 주소와 쿠키를 돌려준다. 시도 제한을 넘으면 429, 설정이 없으면 503. */
  public Start start(HttpServletRequest request) {
    Instant now = clock.instant();
    RateLimiter.Decision decision = startRateLimiter.tryAcquire(request.getRemoteAddr(), now);
    if (!decision.allowed()) {
      throw new BusinessException(
          HttpStatus.TOO_MANY_REQUESTS,
          RATE_LIMITED_CODE,
          "로그인 시도가 너무 많습니다. 잠시 후 다시 시도해 주세요.",
          null,
          decision.retryAfterSeconds());
    }
    ClientRegistration google = registrations.require();

    OAuth2AuthorizationRequest authorization =
        new DefaultOAuth2AuthorizationRequestResolver(
                new InMemoryClientRegistrationRepository(google))
            .resolve(request, google.getRegistrationId());
    String key = tokens.generate();
    Instant expiresAt = authorizationStore.save(hasher.hashToken(key), authorization, now);

    return new Start(
        authorization.getAuthorizationRequestUri(),
        authorizationCookie(key, Duration.between(now, expiresAt)));
  }

  /**
   * callback 결과.
   *
   * @param location 브라우저를 보낼 화면 경로
   * @param signupCookie 처음 온 사용자에게 주는 가입 대기 쿠키. 그 밖에는 {@code null}
   */
  public record Callback(String location, ResponseCookie signupCookie) {}

  /**
   * Google 에서 돌아온 요청을 처리하고 브라우저를 보낼 화면 경로를 돌려준다. 실패해도 예외를 던지지 않는다.
   *
   * <ol>
   *   <li>인가 요청 쿠키로 시작 때 보관한 요청을 꺼낸다(1회용). 없거나 만료·재사용·state 불일치면 {@code STATE_INVALID}.
   *   <li>Google 이 오류를 보냈으면 취소({@code access_denied})와 그 밖의 실패를 나눈다.
   *   <li>code 를 교환하고 ID 토큰을 검증한다. Google 에 닿지 못하면 {@code UNAVAILABLE}, 그 밖은 {@code FAILED}.
   *   <li>Google 이 확인한 이메일이 아니면 {@code FAILED}.
   *   <li>연결된 회원이면 세션을 만들고 메인으로, 같은 이메일의 회원이 있으면 {@code ACCOUNT_LINK_REQUIRED}, 처음 온 사용자는 회원을 만들지
   *       않고 가입 대기를 저장해 추가 정보 화면으로 보낸다.
   * </ol>
   *
   * @param key 인가 요청 쿠키 값 (없으면 {@code null})
   */
  public Callback callback(
      String key,
      String state,
      String code,
      String error,
      HttpServletRequest request,
      HttpServletResponse response) {
    try {
      OidcUser google = verify(key, state, code, error);
      Callback result = signIn(google, request, response);
      log.info("Google 로그인 처리: {}", result.location());
      return result;
    } catch (Failure failure) {
      log.info("Google 로그인 실패: {}", failure.reason.code());
      return failed(failure.reason);
    } catch (RuntimeException e) {
      // DB·세션 저장소 장애 등. 화면 이동 중이라 JSON 오류 대신 로그인 화면으로 보낸다. 세션은 establish 가 실패 시 정리한다
      log.error("Google 로그인 처리 중 오류", e);
      return failed(GoogleAuthFailure.UNAVAILABLE);
    }
  }

  private static Callback failed(GoogleAuthFailure reason) {
    return new Callback(LOGIN_LOCATION + "?error=" + reason.code(), null);
  }

  /** 가입 대기를 조회한다. 쿠키가 없거나 대기가 없음·만료면 410 {@code USERS_GOOGLE_SIGNUP_EXPIRED}. */
  public GoogleSignupPendingResponse pendingSignup(String key) {
    if (!StringUtils.hasText(key)) {
      throw signupExpired();
    }
    GoogleSignupStore.Pending pending =
        signupStore
            .find(hasher.hashToken(key), clock.instant())
            .orElseThrow(GoogleLoginService::signupExpired);
    return new GoogleSignupPendingResponse(pending.email(), pending.name(), pending.expiresAt());
  }

  /** 가입 대기가 없거나 만료·이미 사용. 가입 대기 조회와 가입 완료가 같이 쓴다. */
  static BusinessException signupExpired() {
    return new BusinessException(
        HttpStatus.GONE, SIGNUP_EXPIRED_CODE, "가입 시간이 지났습니다. Google 로 다시 시작해 주세요.");
  }

  private OidcUser verify(String key, String state, String code, String error) {
    if (!registrations.available()) {
      throw new Failure(GoogleAuthFailure.UNAVAILABLE);
    }
    if (!StringUtils.hasText(key) || !StringUtils.hasText(state)) {
      throw new Failure(GoogleAuthFailure.STATE_INVALID);
    }
    OAuth2AuthorizationRequest authorization =
        authorizationStore
            .take(hasher.hashToken(key), clock.instant())
            .filter(a -> state.equals(a.getState()))
            .orElseThrow(() -> new Failure(GoogleAuthFailure.STATE_INVALID));

    if (error != null || !StringUtils.hasText(code)) {
      // code 와 error 를 함께 보낸 응답은 받지 않는다
      boolean cancelled = ACCESS_DENIED.equals(error) && code == null;
      throw new Failure(cancelled ? GoogleAuthFailure.CANCELLED : GoogleAuthFailure.FAILED);
    }

    OidcUser google;
    try {
      google = authenticator.authenticate(registrations.require(), authorization, state, code);
    } catch (OAuth2AuthenticationException e) {
      if (unavailable(e)) {
        log.warn("Google 호출 실패: {}", e.getError().getErrorCode(), e);
        throw new Failure(GoogleAuthFailure.UNAVAILABLE);
      }
      log.warn("Google 토큰 교환·검증 실패: {}", e.getError().getErrorCode());
      throw new Failure(GoogleAuthFailure.FAILED);
    }
    if (!Boolean.TRUE.equals(google.getEmailVerified())
        || !StringUtils.hasText(google.getEmail())) {
      throw new Failure(GoogleAuthFailure.FAILED);
    }
    return google;
  }

  private Callback signIn(
      OidcUser google, HttpServletRequest request, HttpServletResponse response) {
    Optional<UserIdentity> identity =
        identityRepository.findByProviderAndProviderSubject(
            AuthProvider.GOOGLE, google.getSubject());
    if (identity.isPresent()) {
      sessionEstablisher.establish(identity.get().getUser(), request, response);
      return new Callback(SIGNED_IN_LOCATION, null);
    }
    String email = EmailNormalizer.normalize(google.getEmail());
    if (userRepository.existsByEmail(email)) {
      // 같은 이메일의 자체 계정이나 다른 Google 계정으로 가입한 회원. 자동으로 연결하지 않는다
      throw new Failure(GoogleAuthFailure.ACCOUNT_LINK_REQUIRED);
    }
    // 처음 온 사용자. 동의 없이 회원을 만들지 않으므로 가입 대기만 저장하고 추가 정보 화면으로 보낸다
    Instant now = clock.instant();
    String key = tokens.generate();
    GoogleSignupStore.Pending pending =
        signupStore.save(
            hasher.hashToken(key),
            google.getSubject(),
            email,
            StringUtils.hasText(google.getFullName()) ? google.getFullName() : null,
            now);
    return new Callback(
        SIGNUP_LOCATION, laxCookie(SIGNUP_COOKIE, key, Duration.between(now, pending.expiresAt())));
  }

  /** Google 에 닿지 못했거나 Google 이 서버 오류를 냈다. 사용자 입력이나 토큰 문제가 아니다. */
  private static boolean unavailable(Throwable e) {
    for (Throwable t = e; t != null; t = t.getCause()) {
      if (t instanceof ResourceAccessException
          || t instanceof IOException
          || t instanceof HttpServerErrorException) {
        return true;
      }
    }
    return false;
  }

  /** 인가 요청 쿠키를 지우는 쿠키. callback 은 결과와 상관없이 쿠키를 지운다(인가 요청은 이미 꺼냈다). */
  public static ResponseCookie expiredAuthorizationCookie() {
    return laxCookie(AUTHORIZATION_COOKIE, "", Duration.ZERO);
  }

  /** 가입 대기 쿠키를 지우는 쿠키. 가입을 마치면 지운다. 실패 응답에 남은 쿠키는 가리키는 대기가 없거나(409·410) 다시 쓸 대기다(400). */
  public static ResponseCookie expiredSignupCookie() {
    return laxCookie(SIGNUP_COOKIE, "", Duration.ZERO);
  }

  private static ResponseCookie authorizationCookie(String value, Duration maxAge) {
    return laxCookie(AUTHORIZATION_COOKIE, value, maxAge);
  }

  /** Google 로그인 임시 쿠키. 교차 사이트 리다이렉트에서 발급·사용하므로 세션 쿠키(Strict)와 달리 Lax 다. */
  private static ResponseCookie laxCookie(String name, String value, Duration maxAge) {
    return ResponseCookie.from(name, value)
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .path("/")
        .maxAge(maxAge)
        .build();
  }

  /** callback 을 로그인 화면으로 돌려보내는 실패. 이 클래스 밖으로 나가지 않는다. */
  private static final class Failure extends RuntimeException {
    private final GoogleAuthFailure reason;

    Failure(GoogleAuthFailure reason) {
      super(reason.code(), null, false, false);
      this.reason = reason;
    }
  }
}
