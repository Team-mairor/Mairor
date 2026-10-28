package com.mairor.backend.users.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.ratelimit.RateLimiter;
import com.mairor.backend.users.dto.request.EmailAvailabilityRequest;
import com.mairor.backend.users.dto.response.EmailAvailabilityResponse;
import com.mairor.backend.users.repository.UserRepository;
import java.time.Clock;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

/**
 * 가입 가능 이메일 확인 (API-USERS-011). 이메일 가입 여부를 알려 주므로 클라이언트마다 요청 횟수를 제한한다. 형식이 틀린 요청은 컨트롤러 검증에서 먼저 거절되어
 * 횟수에 더해지지 않는다.
 */
@Service
public class EmailAvailabilityService {

  static final String RATE_LIMITED_CODE = "USERS_EMAIL_CHECK_RATE_LIMITED";

  private final UserRepository userRepository;
  private final RateLimiter rateLimiter;
  private final Clock clock;

  public EmailAvailabilityService(
      UserRepository userRepository,
      @Qualifier("emailAvailabilityRateLimiter") RateLimiter rateLimiter,
      Clock clock) {
    this.userRepository = userRepository;
    this.rateLimiter = rateLimiter;
    this.clock = clock;
  }

  /**
   * @param clientKey 요청 제한의 기준이 되는 클라이언트 식별값(IP)
   */
  public EmailAvailabilityResponse check(EmailAvailabilityRequest request, String clientKey) {
    RateLimiter.Decision decision = rateLimiter.tryAcquire(clientKey, clock.instant());
    if (!decision.allowed()) {
      throw new BusinessException(
          HttpStatus.TOO_MANY_REQUESTS,
          RATE_LIMITED_CODE,
          ErrorCode.TOO_MANY_REQUESTS.message(),
          null,
          decision.retryAfterSeconds());
    }
    return new EmailAvailabilityResponse(
        request.email(), !userRepository.existsByEmail(request.email()));
  }
}
