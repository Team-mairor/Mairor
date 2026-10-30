package com.mairor.backend.users.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.common.mail.MailDeliveryException;
import com.mairor.backend.common.mail.PasswordResetMailSender;
import com.mairor.backend.common.ratelimit.RateLimiter;
import com.mairor.backend.users.dto.request.PasswordResetPasswordRequest;
import com.mairor.backend.users.dto.request.PasswordResetRequest;
import com.mairor.backend.users.dto.request.PasswordResetVerificationRequest;
import com.mairor.backend.users.dto.response.PasswordResetSentResponse;
import com.mairor.backend.users.dto.response.PasswordResetVerifiedResponse;
import com.mairor.backend.users.entity.User;
import com.mairor.backend.users.repository.UserRepository;
import com.mairor.backend.users.support.EmailVerificationStore;
import com.mairor.backend.users.support.EmailVerificationStore.ConfirmOutcome;
import com.mairor.backend.users.support.EmailVerificationStore.IssuedToken;
import com.mairor.backend.users.support.EmailVerificationStore.SendPermit;
import com.mairor.backend.users.support.EmailVerificationStoreConfig;
import com.mairor.backend.users.support.LoginAttemptLimiter;
import com.mairor.backend.users.support.PasswordNormalizer;
import com.mairor.backend.users.support.PasswordResetLocks;
import com.mairor.backend.users.support.PasswordResetMetrics;
import com.mairor.backend.users.support.PasswordResetProperties;
import com.mairor.backend.users.support.VerificationCodeGenerator;
import com.mairor.backend.users.support.VerificationHasher;
import com.mairor.backend.users.support.VerificationTokens;
import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

/**
 * 비밀번호 재설정 (API-USERS-008 인증번호 발송, API-USERS-009 인증번호 확인, API-USERS-010 새 비밀번호 저장). 인증번호와 토큰은 해시로만
 * 저장하고 로그에 남기지 않는다.
 *
 * <p><b>가입 여부를 응답으로 드러내지 않는다.</b> 가입하지 않았거나 비밀번호가 없는 이메일에도 아무도 맞힐 수 없는 인증번호를 저장해서, 발송·확인이 가입한 이메일과
 * 똑같이 동작한다. 응답 시간 차이와, 메일을 보내는 가입 이메일에서만 생기는 발송 실패(503)로는 드러날 수 있다(허용한 예외, README "비밀번호 재설정").
 *
 * <p>같은 이메일의 요청은 한 번에 하나만 실행한다({@link PasswordResetLocks}). 틀린 시도 횟수는 예외를 던져도 남아야 해서
 * {@code @Transactional}을 걸지 않는다.
 */
@Service
public class PasswordResetService {

  static final String RATE_LIMITED = "USERS_RESET_RATE_LIMITED";
  static final String SEND_FAILED = "USERS_RESET_SEND_FAILED";
  static final String CODE_INVALID = "USERS_RESET_CODE_INVALID";
  static final String CODE_EXPIRED = "USERS_RESET_CODE_EXPIRED";
  static final String ATTEMPTS_EXCEEDED = "USERS_RESET_CODE_ATTEMPTS_EXCEEDED";
  static final String TOKEN_EXPIRED = "USERS_RESET_TOKEN_EXPIRED";

  private static final Logger log = LoggerFactory.getLogger(PasswordResetService.class);

  private final UserRepository userRepository;
  private final EmailVerificationStore store;
  private final VerificationHasher hasher;
  private final VerificationCodeGenerator codeGenerator;
  private final VerificationTokens tokens;
  private final PasswordResetMailSender mailSender;
  private final RateLimiter sendRateLimiter;
  private final PasswordResetLocks locks;
  private final PasswordResetProperties properties;
  private final PasswordEncoder passwordEncoder;
  private final UserSessionService userSessionService;
  private final LoginAttemptLimiter loginAttemptLimiter;
  private final PasswordResetMetrics metrics;
  private final Clock clock;

  public PasswordResetService(
      UserRepository userRepository,
      @Qualifier(EmailVerificationStoreConfig.PASSWORD_RESET) EmailVerificationStore store,
      VerificationHasher hasher,
      VerificationCodeGenerator codeGenerator,
      VerificationTokens tokens,
      PasswordResetMailSender mailSender,
      @Qualifier("passwordResetRateLimiter") RateLimiter sendRateLimiter,
      PasswordResetLocks locks,
      PasswordResetProperties properties,
      PasswordEncoder passwordEncoder,
      UserSessionService userSessionService,
      LoginAttemptLimiter loginAttemptLimiter,
      PasswordResetMetrics metrics,
      Clock clock) {
    this.userRepository = userRepository;
    this.store = store;
    this.hasher = hasher;
    this.codeGenerator = codeGenerator;
    this.tokens = tokens;
    this.mailSender = mailSender;
    this.sendRateLimiter = sendRateLimiter;
    this.locks = locks;
    this.properties = properties;
    this.passwordEncoder = passwordEncoder;
    this.userSessionService = userSessionService;
    this.loginAttemptLimiter = loginAttemptLimiter;
    this.metrics = metrics;
    this.clock = clock;
  }

  /** 발송할 메일. 가입하지 않은 이메일에는 아무것도 보내지 않는다. */
  private sealed interface Delivery {
    record ResetCode(String code) implements Delivery {}

    record GoogleNotice() implements Delivery {}

    record Nothing() implements Delivery {}
  }

  /**
   * 인증번호를 만들어 메일로 보낸다. 메일은 잠금을 푼 뒤 보낸다: SMTP 가 느려서 잠금 안에서 보내면 그동안 같은 이메일의 확인·저장이 거절된다.
   *
   * <p>재발송 예약 뒤에 무엇이 실패하든 그 세대의 예약만 되돌려 쿨다운·시간당 횟수가 줄지 않게 한다(그사이 다른 요청이 저장한 인증번호는 건드리지 않는다). 메일 발송
   * 실패만 503 으로 바꾼다.
   *
   * <p>응답의 유효 시간은 메일 발송에 걸린 시간을 빼지 않은 설정값 전체다. 빼서 돌려주면 메일을 보낸 가입 이메일만 숫자가 작아져 가입 여부가 드러난다. 차이는 SMTP
   * 시간 제한만큼(수 초)이고, 만료는 서버가 저장 시각 기준으로 판단한다.
   *
   * <p>IP 요청 제한은 잠금보다 먼저 확인한다. 그래서 잠금 충돌로 거절된 요청도 IP 횟수를 쓴다. 순서를 바꾸면 IP 한도를 다 쓴 요청도 피해자 이메일의 잠금을 계속
   * 잡아 정상 요청을 429 로 밀어낼 수 있다.
   *
   * @param clientKey 요청 제한의 기준이 되는 클라이언트 식별값(IP)
   */
  public PasswordResetSentResponse send(PasswordResetRequest request, String clientKey) {
    Instant now = clock.instant();
    RateLimiter.Decision decision = sendRateLimiter.tryAcquire(clientKey, now);
    if (!decision.allowed()) {
      throw rateLimited(decision.retryAfterSeconds());
    }
    String email = request.email();
    SendPermit permit;
    Delivery delivery;
    try (PasswordResetLocks.Held ignored = lockOrReject(email)) {
      permit = store.reserveSend(email, now);
      if (!permit.isAllowed()) {
        throw rateLimited(permit.retryAfterSeconds());
      }
      try {
        delivery = saveCode(email, now, permit.generation());
      } catch (RuntimeException e) {
        cancel(email, permit.generation(), e);
        throw e;
      }
    }

    try {
      deliver(email, delivery);
    } catch (MailDeliveryException e) {
      BusinessException failed =
          new BusinessException(
              HttpStatus.SERVICE_UNAVAILABLE,
              SEND_FAILED,
              "비밀번호 재설정 메일을 보내지 못했습니다. 잠시 후 다시 시도해 주세요.");
      cancel(email, permit.generation(), failed);
      throw failed;
    } catch (RuntimeException e) {
      cancel(email, permit.generation(), e);
      throw e;
    }
    return new PasswordResetSentResponse(
        properties.codeTtl().toSeconds(), properties.resendCooldown().toSeconds());
  }

  /**
   * 인증번호를 확인하고, 맞으면 새 비밀번호 저장에 쓸 토큰을 발급한다. 잠금 안에서 해서, 진행 중인 새 비밀번호 저장이 정리를 마친 뒤에 토큰이 새로 생기는 틈이 없다.
   */
  public PasswordResetVerifiedResponse verify(PasswordResetVerificationRequest request) {
    String email = request.email();
    try (PasswordResetLocks.Held ignored = lockOrReject(email)) {
      Instant now = clock.instant();
      ConfirmOutcome outcome =
          store.confirmCode(
              email, hasher.hashCode(email, request.code()), now, properties.maxAttempts());
      return switch (outcome) {
        case OK -> issueToken(email, now);
        case MISMATCH ->
            throw new BusinessException(HttpStatus.BAD_REQUEST, CODE_INVALID, "인증번호가 일치하지 않습니다.");
        case EXPIRED_OR_MISSING ->
            throw new BusinessException(
                HttpStatus.GONE, CODE_EXPIRED, "인증번호가 만료되었거나 요청 기록이 없습니다. 다시 받아 주세요.");
        case ATTEMPTS_EXCEEDED ->
            throw new BusinessException(
                HttpStatus.TOO_MANY_REQUESTS,
                ATTEMPTS_EXCEEDED,
                "인증번호를 너무 많이 틀렸습니다. 인증번호를 다시 받아 주세요.");
      };
    }
  }

  /**
   * 새 비밀번호를 저장하고 이 회원의 모든 세션을 끝낸다. 자동 로그인은 하지 않는다.
   *
   * <ul>
   *   <li>입력이 틀리면 토큰을 쓰지 않는다.
   *   <li>잠금을 잡은 뒤 토큰을 다시 확인한다. 조회와 잠금 사이에 토큰이 바뀌거나 다 쓰였으면 바꾸지 않는다.
   *   <li>비밀번호와 버전을 먼저 커밋하고 세션을 끝낸다. 반대면 그 사이 옛 비밀번호로 로그인할 수 있다.
   *   <li>로그인 잠금 해제와 토큰·인증번호 폐기는 세션 정리까지 끝난 뒤에 한다.
   * </ul>
   *
   * <p>세션 정리가 도중에 실패하면 비밀번호는 이미 바뀐 채 원래 예외가 나간다(응답은 원인에 따라 503 또는 500). 토큰은 남아 있으므로 같은 요청을 다시 보내면
   * 비밀번호를 한 번 더 저장하고 남은 세션을 끝내 마무리된다. 토큰이 그사이 만료·교체·퇴거됐으면 인증번호를 다시 받아야 한다.
   *
   * @param currentUserId 요청을 보낸 세션의 로그인 회원 ID. 로그인하지 않았으면 {@code null}
   * @param currentSessionId 요청을 보낸 세션 ID. 없으면 {@code null}
   * @return 요청을 보낸 세션도 끝냈으면 {@code true}. 호출자는 그 세션이 응답 커밋 때 되살아나지 않도록 따로 끝내야 한다
   */
  public boolean resetPassword(
      PasswordResetPasswordRequest request, UUID currentUserId, String currentSessionId) {
    String password = PasswordNormalizer.normalize(request.newPassword());
    if (!password.equals(PasswordNormalizer.normalize(request.newPasswordConfirm()))) {
      throw passwordMismatch();
    }
    String tokenHash = hasher.hashToken(request.resetToken());
    String email = store.findTokenEmail(tokenHash, clock.instant()).orElseThrow(this::tokenExpired);

    try (PasswordResetLocks.Held ignored = lockOrReject(email)) {
      Instant now = clock.instant();
      IssuedToken issued =
          store
              .findToken(tokenHash, now)
              .filter(token -> token.email().equals(email))
              .orElseThrow(this::tokenExpired);
      User user = userRepository.findByEmail(email).orElse(null);
      if (user == null || user.getPasswordHash() == null) {
        throw tokenExpired();
      }
      // 이 토큰으로 아직 바꾼 적이 없을 때만(버전이 발급 때 그대로) 현재 비밀번호와 같은지 본다. 이미 바꿨다면 세션 정리 실패 뒤의 재시도라 같은 비밀번호로 마무리할
      // 수 있어야 한다
      if (user.getPasswordVersion() == issued.stamp()
          && passwordEncoder.matches(password, user.getPasswordHash())) {
        throw sameAsCurrentPassword();
      }
      // 트랜잭션(DB 커넥션) 밖에서 계산한다. 잠금 안이라 한 토큰으로 계산을 쌓을 수 없다
      String hash = passwordEncoder.encode(password);
      if (userRepository.updatePassword(user.getId(), hash, now) != 1) {
        // 조회한 뒤 회원이 사라져 바뀐 것이 없다. 세션·토큰은 건드리지 않는다
        throw tokenExpired();
      }

      String endingCurrent = user.getId().equals(currentUserId) ? currentSessionId : null;
      try {
        userSessionService.revokeAll(user.getId(), endingCurrent);
      } catch (RuntimeException e) {
        metrics.record(PasswordResetMetrics.Result.SESSION_REVOKE_FAILED);
        log.error(
            "비밀번호를 바꿨지만 기존 세션을 모두 끝내지 못했습니다. 같은 재설정 토큰으로 다시 요청하면 마무리됩니다. 원인={}",
            e.getClass().getSimpleName());
        throw e;
      }
      loginAttemptLimiter.reset(email);
      store.invalidateAll(email);
      metrics.record(PasswordResetMetrics.Result.SUCCESS);
      return endingCurrent != null;
    }
  }

  /** 보낼 메일을 정하고 인증번호를 저장한다. 비밀번호가 있는 회원만 진짜 인증번호를 받는다. */
  private Delivery saveCode(String email, Instant now, long generation) {
    User user = userRepository.findByEmail(email).orElse(null);
    Instant expiresAt = now.plus(properties.codeTtl());
    if (user != null && user.getPasswordHash() != null) {
      String code = codeGenerator.generate();
      store.saveCode(email, hasher.hashCode(email, code), expiresAt, generation);
      return new Delivery.ResetCode(code);
    }
    store.saveCode(email, hasher.decoyCodeHash(), expiresAt, generation);
    return user != null ? new Delivery.GoogleNotice() : new Delivery.Nothing();
  }

  private void deliver(String email, Delivery delivery) {
    switch (delivery) {
      case Delivery.ResetCode resetCode ->
          mailSender.sendResetCode(email, resetCode.code(), properties.codeTtl());
      case Delivery.GoogleNotice ignored -> mailSender.sendGoogleAccountNotice(email);
      case Delivery.Nothing ignored -> {}
    }
  }

  /** 토큰을 발급한다. 발급 시점의 비밀번호 버전을 함께 저장해, 새 비밀번호 저장이 이 토큰의 첫 시도인지 재시도인지 가린다. */
  private PasswordResetVerifiedResponse issueToken(String email, Instant now) {
    String token = tokens.generate();
    Instant expiresAt = now.plus(properties.tokenTtl());
    int passwordVersion = userRepository.findByEmail(email).map(User::getPasswordVersion).orElse(0);
    store.saveToken(hasher.hashToken(token), email, passwordVersion, expiresAt);
    return new PasswordResetVerifiedResponse(token, expiresAt);
  }

  /** 그 세대의 발송 예약을 되돌린다. 실패하면 원래 예외에 붙여 원래 예외를 가리지 않는다. */
  private void cancel(String email, long generation, RuntimeException cause) {
    try {
      store.cancelSend(email, generation);
    } catch (RuntimeException cancelFailure) {
      cause.addSuppressed(cancelFailure);
    }
  }

  /** 같은 이메일의 다른 재설정 요청이 진행 중이면 기다리지 않고 429 로 거절한다. */
  private PasswordResetLocks.Held lockOrReject(String email) {
    return locks
        .tryLock(email)
        .orElseThrow(
            () -> {
              metrics.record(PasswordResetMetrics.Result.BUSY);
              return BusinessException.tooManyRequests(1);
            });
  }

  private BusinessException tokenExpired() {
    return new BusinessException(
        HttpStatus.GONE, TOKEN_EXPIRED, "재설정 시간이 지났거나 이미 사용한 요청입니다. 인증번호를 다시 받아 주세요.");
  }

  private static BusinessException sameAsCurrentPassword() {
    return new BusinessException(
        HttpStatus.BAD_REQUEST,
        ErrorCode.VALIDATION_FAILED.name(),
        ErrorCode.VALIDATION_FAILED.message(),
        List.of(new ErrorResponse.FieldError("newPassword", "현재 비밀번호와 다른 비밀번호를 입력해 주세요.")),
        null);
  }

  private static BusinessException passwordMismatch() {
    return new BusinessException(
        HttpStatus.BAD_REQUEST,
        ErrorCode.VALIDATION_FAILED.name(),
        ErrorCode.VALIDATION_FAILED.message(),
        List.of(new ErrorResponse.FieldError("newPasswordConfirm", "비밀번호와 일치하지 않습니다.")),
        null);
  }

  private static BusinessException rateLimited(long retryAfterSeconds) {
    return new BusinessException(
        HttpStatus.TOO_MANY_REQUESTS,
        RATE_LIMITED,
        ErrorCode.TOO_MANY_REQUESTS.message(),
        null,
        retryAfterSeconds);
  }
}
