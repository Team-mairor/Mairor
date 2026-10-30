package com.mairor.backend.users.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.users.dto.request.LoginRequest;
import com.mairor.backend.users.dto.response.LoginResponse;
import com.mairor.backend.users.dto.response.UserResponse;
import com.mairor.backend.users.entity.User;
import com.mairor.backend.users.repository.UserRepository;
import com.mairor.backend.users.support.LoginAttemptLimiter;
import com.mairor.backend.users.support.LoginAttemptLimiter.Allowed;
import com.mairor.backend.users.support.LoginAttemptLimiter.Locked;
import com.mairor.backend.users.support.LoginAttemptLimiter.Pending;
import com.mairor.backend.users.support.LoginAttemptLimiter.Result;
import com.mairor.backend.users.support.LoginAttemptLimiter.Saturated;
import com.mairor.backend.users.support.LoginAttemptLimiter.Ticket;
import com.mairor.backend.users.support.LoginHashGate;
import com.mairor.backend.users.support.LoginMetrics;
import com.mairor.backend.users.support.PasswordNormalizer;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.util.Optional;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

/**
 * 자체 로그인 (API-USERS-002). 이메일·비밀번호를 확인하고 서버 세션을 만든다.
 *
 * <p>처리 순서: 시도 제한({@link LoginAttemptLimiter})에서 자리를 잡는다 → 사용자를 조회한다 → 비밀번호를 검증한다 → 틀리면 실패로, 맞으면
 * 성공으로 시도를 종료하고 세션을 만든다. 시도 ticket 은 어떤 경로(예외 포함)에서도 정확히 한 번 종료한다. 자격 증명과 무관한 내부 오류나 BCrypt 상한 거절은
 * 환불해서 실패로 세지 않는다.
 *
 * <p>실패 원인은 구분하지 않는다. 미가입 이메일, 틀린 비밀번호, 비밀번호가 없는 Google 전용 계정, 72바이트를 넘는 비밀번호가 모두 같은 401 이다. 사용자나
 * 해시가 없어도 더미 해시와 비교해서 응답 시간 차이로 가입 여부가 드러나는 것을 줄인다.
 *
 * <p>서비스 메서드 전체에 {@code @Transactional} 을 걸지 않는다. BCrypt 계산(수백 ms) 동안 DB 커넥션을 쥐지 않기 위해서다. 조회는
 * 리포지토리의 기본 트랜잭션으로 충분하다.
 */
@Service
public class UserLoginService {

  /** BCrypt 는 입력의 72바이트 뒤를 조용히 무시한다. 그 이상은 비교하지 않고 실패로 처리한다. */
  static final int MAX_PASSWORD_BYTES = 72;

  private static final String INVALID_CREDENTIALS_CODE = "USERS_INVALID_CREDENTIALS";
  private static final String INVALID_CREDENTIALS_MESSAGE = "이메일 또는 비밀번호를 확인해 주세요.";
  private static final String RATE_LIMITED_CODE = "USERS_LOGIN_RATE_LIMITED";
  private static final String RATE_LIMITED_MESSAGE = "로그인 시도가 너무 많습니다. 잠시 후 다시 시도해 주세요.";

  private final UserRepository userRepository;
  private final PasswordEncoder passwordEncoder;
  private final LoginAttemptLimiter limiter;
  private final LoginHashGate hashGate;
  private final SessionEstablisher sessionEstablisher;
  private final LoginMetrics metrics;
  private final Clock clock;

  /** 존재하지 않는 사용자에도 같은 비용의 해시 비교를 하기 위한 더미 해시. */
  private final String dummyHash;

  public UserLoginService(
      UserRepository userRepository,
      PasswordEncoder passwordEncoder,
      LoginAttemptLimiter limiter,
      LoginHashGate hashGate,
      SessionEstablisher sessionEstablisher,
      LoginMetrics metrics,
      Clock clock) {
    this.userRepository = userRepository;
    this.passwordEncoder = passwordEncoder;
    this.limiter = limiter;
    this.hashGate = hashGate;
    this.sessionEstablisher = sessionEstablisher;
    this.metrics = metrics;
    this.clock = clock;
    this.dummyHash = passwordEncoder.encode(UUID.randomUUID().toString());
  }

  public LoginResponse login(
      LoginRequest request, HttpServletRequest httpRequest, HttpServletResponse httpResponse) {
    Ticket ticket = acquire(request.email());
    try {
      User user = authenticate(request, ticket);
      limiter.succeed(ticket);
      String csrfToken = sessionEstablisher.establish(user, httpRequest, httpResponse);
      metrics.record(LoginMetrics.Result.SUCCESS);
      return new LoginResponse(UserResponse.from(user), csrfToken);
    } catch (BusinessException e) {
      // 거절 사유는 던지는 곳에서 이미 센다
      throw e;
    } catch (RuntimeException e) {
      metrics.record(LoginMetrics.Result.ERROR);
      throw e;
    } finally {
      // 이미 종료된 ticket 이면 아무 일도 하지 않는다. 예외로 빠져나온 경우에만 환불된다
      limiter.refund(ticket);
    }
  }

  private Ticket acquire(String email) {
    Result result = limiter.tryAcquire(email, clock.instant());
    return switch (result) {
      case Allowed allowed -> allowed.ticket();
      case Locked locked ->
          throw rejected(LoginMetrics.Result.LOCKED, rateLimited(locked.retryAfterSeconds()));
      case Pending pending ->
          throw rejected(LoginMetrics.Result.PENDING, rateLimited(pending.retryAfterSeconds()));
      case Saturated saturated ->
          throw rejected(LoginMetrics.Result.SATURATED, rateLimited(saturated.retryAfterSeconds()));
    };
  }

  /**
   * 비밀번호를 검증한다. 틀리면 실패로 종료하고 401 을 던진다. 맞으면 사용자를 돌려준다.
   *
   * <p>사용자 조회부터 BCrypt 비교까지를 해시 게이트 안에서 한다. 게이트가 BCrypt 계산만 막으면, 서로 다른 이메일 요청이 몰릴 때 사용자 조회가 DB 연결을
   * 기다리며 쌓이기 때문이다. 게이트가 가득 차면 DB 에 가지 않고 바로 429 로 거절한다. 72바이트를 넘는 비밀번호는 어차피 실패이므로 조회도 하지 않는다.
   */
  private User authenticate(LoginRequest request, Ticket ticket) {
    String password = PasswordNormalizer.normalize(request.password());
    User user =
        password.getBytes(StandardCharsets.UTF_8).length > MAX_PASSWORD_BYTES
            ? null
            : verified(request.email(), password);
    if (user == null) {
      limiter.fail(ticket, clock.instant());
      metrics.record(LoginMetrics.Result.INVALID_CREDENTIALS);
      throw invalidCredentials();
    }
    return user;
  }

  /**
   * 사용자를 조회하고 비밀번호가 맞으면 사용자를, 아니면 {@code null} 을 돌려준다. 사용자가 없거나 해시가 없으면(Google 전용) 더미 해시와 비교해서 응답
   * 시간 차이로 가입 여부가 드러나는 것을 줄인다. 게이트에 자리가 없으면 429 를 던진다(시도 환불은 {@link #login} 의 {@code finally} 가
   * 한다).
   */
  private User verified(String email, String password) {
    Optional<LoginHashGate.Permit> permit = hashGate.tryEnter();
    if (permit.isEmpty()) {
      throw rejected(LoginMetrics.Result.GATE_REJECTED, BusinessException.tooManyRequests(1));
    }
    try (LoginHashGate.Permit ignored = permit.get()) {
      User user = userRepository.findByEmail(email).orElse(null);
      String hash = user == null ? null : user.getPasswordHash();
      if (hash == null) {
        passwordEncoder.matches(password, dummyHash);
        return null;
      }
      return passwordEncoder.matches(password, hash) ? user : null;
    }
  }

  /** 거절 사유를 지표로 세고 같은 예외를 돌려준다. */
  private BusinessException rejected(LoginMetrics.Result result, BusinessException e) {
    metrics.record(result);
    return e;
  }

  private static BusinessException invalidCredentials() {
    return new BusinessException(
        HttpStatus.UNAUTHORIZED, INVALID_CREDENTIALS_CODE, INVALID_CREDENTIALS_MESSAGE);
  }

  private static BusinessException rateLimited(long retryAfterSeconds) {
    return new BusinessException(
        HttpStatus.TOO_MANY_REQUESTS,
        RATE_LIMITED_CODE,
        RATE_LIMITED_MESSAGE,
        null,
        retryAfterSeconds);
  }
}
