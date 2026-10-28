package com.mairor.backend.users.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.mail.MailDeliveryException;
import com.mairor.backend.common.mail.VerificationMailSender;
import com.mairor.backend.common.ratelimit.RateLimiter;
import com.mairor.backend.users.dto.request.EmailVerificationConfirmRequest;
import com.mairor.backend.users.dto.request.EmailVerificationRequest;
import com.mairor.backend.users.dto.response.EmailVerificationSentResponse;
import com.mairor.backend.users.dto.response.EmailVerifiedResponse;
import com.mairor.backend.users.repository.UserRepository;
import com.mairor.backend.users.support.EmailVerificationProperties;
import com.mairor.backend.users.support.EmailVerificationStore;
import com.mairor.backend.users.support.EmailVerificationStore.ConfirmOutcome;
import com.mairor.backend.users.support.EmailVerificationStore.SendPermit;
import com.mairor.backend.users.support.VerificationCodeGenerator;
import com.mairor.backend.users.support.VerificationHasher;
import com.mairor.backend.users.support.VerificationTokens;
import java.time.Clock;
import java.time.Instant;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

/**
 * 가입 이메일 소유 확인 (API-USERS-012 발송, API-USERS-013 확인). 인증번호와 토큰은 해시로만 저장하고 로그에 남기지 않는다.
 *
 * <p>인증 상태는 DB 가 아니라 {@link EmailVerificationStore}에 있고, 틀린 시도 횟수는 예외를 던져도 남아야 해서
 * {@code @Transactional}을 걸지 않는다.
 */
@Service
public class EmailVerificationService {

  static final String RATE_LIMITED = "USERS_EMAIL_SEND_RATE_LIMITED";
  static final String SEND_FAILED = "USERS_EMAIL_SEND_FAILED";
  static final String CODE_INVALID = "USERS_EMAIL_CODE_INVALID";
  static final String CODE_EXPIRED = "USERS_EMAIL_CODE_EXPIRED";
  static final String ATTEMPTS_EXCEEDED = "USERS_EMAIL_CODE_ATTEMPTS_EXCEEDED";
  private static final String EMAIL_DUPLICATE = "USERS_EMAIL_DUPLICATE";

  private final UserRepository userRepository;
  private final EmailVerificationStore store;
  private final VerificationHasher hasher;
  private final VerificationCodeGenerator codeGenerator;
  private final VerificationTokens tokens;
  private final VerificationMailSender mailSender;
  private final RateLimiter sendRateLimiter;
  private final EmailVerificationProperties properties;
  private final Clock clock;

  public EmailVerificationService(
      UserRepository userRepository,
      EmailVerificationStore store,
      VerificationHasher hasher,
      VerificationCodeGenerator codeGenerator,
      VerificationTokens tokens,
      VerificationMailSender mailSender,
      @Qualifier("emailVerificationRateLimiter") RateLimiter sendRateLimiter,
      EmailVerificationProperties properties,
      Clock clock) {
    this.userRepository = userRepository;
    this.store = store;
    this.hasher = hasher;
    this.codeGenerator = codeGenerator;
    this.tokens = tokens;
    this.mailSender = mailSender;
    this.sendRateLimiter = sendRateLimiter;
    this.properties = properties;
    this.clock = clock;
  }

  /**
   * 인증번호를 만들어 메일로 보낸다. 클라이언트 요청 제한, 가입 여부, 이메일별 재발송 제한 순으로 확인하고, 메일 발송에 실패하면 저장한 번호와 재발송 기록을 되돌린다.
   *
   * @param clientKey 요청 제한의 기준이 되는 클라이언트 식별값(IP)
   */
  public EmailVerificationSentResponse send(EmailVerificationRequest request, String clientKey) {
    Instant now = clock.instant();
    RateLimiter.Decision decision = sendRateLimiter.tryAcquire(clientKey, now);
    if (!decision.allowed()) {
      throw rateLimited(decision.retryAfterSeconds());
    }
    String email = request.email();
    if (userRepository.existsByEmail(email)) {
      throw new BusinessException(HttpStatus.CONFLICT, EMAIL_DUPLICATE, "이미 가입된 이메일입니다.");
    }
    SendPermit permit = store.reserveSend(email, now);
    if (!permit.isAllowed()) {
      throw rateLimited(permit.retryAfterSeconds());
    }

    String code = codeGenerator.generate();
    store.saveCode(email, hasher.hashCode(email, code), now.plus(properties.codeTtl()));
    try {
      mailSender.send(email, code, properties.codeTtl());
    } catch (MailDeliveryException e) {
      store.cancelSend(email);
      throw new BusinessException(
          HttpStatus.SERVICE_UNAVAILABLE, SEND_FAILED, "인증번호 메일을 보내지 못했습니다. 잠시 후 다시 시도해 주세요.");
    } catch (RuntimeException e) {
      store.cancelSend(email);
      throw e;
    }
    return new EmailVerificationSentResponse(
        properties.codeTtl().toSeconds(), properties.resendCooldown().toSeconds());
  }

  /** 인증번호를 확인하고, 맞으면 가입에 쓸 인증 토큰을 발급한다. */
  public EmailVerifiedResponse confirm(EmailVerificationConfirmRequest request) {
    Instant now = clock.instant();
    String email = request.email();
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

  private EmailVerifiedResponse issueToken(String email, Instant now) {
    String token = tokens.generate();
    Instant expiresAt = now.plus(properties.tokenTtl());
    store.saveToken(hasher.hashToken(token), email, expiresAt);
    return new EmailVerifiedResponse(token, expiresAt);
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
