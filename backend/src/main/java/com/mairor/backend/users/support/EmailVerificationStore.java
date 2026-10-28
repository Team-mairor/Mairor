package com.mairor.backend.users.support;

import java.time.Instant;

/**
 * 가입 이메일 인증의 임시 상태(인증번호, 시도 횟수, 재발송 제한, 인증 토큰) 저장소. 서비스는 이 인터페이스만 보고 구현체({@link
 * InMemoryEmailVerificationStore})를 바꿀 수 있다. 계약은 {@code EmailVerificationStoreContract}로 확인한다.
 *
 * <ul>
 *   <li>모든 연산은 이메일(또는 토큰) 단위로 원자적이다.
 *   <li>인증번호와 토큰은 평문이 아니라 해시({@link VerificationHasher})만 받고, 이메일은 정규화한 값이다.
 *   <li>현재 시각은 호출자가 넘긴다.
 *   <li>만료와 "발송 이력 없음"은 구별하지 않는다.
 * </ul>
 */
public interface EmailVerificationStore {

  /** 인증번호 발송 한 번을 예약한다. 쿨다운과 시간당 한도가 함께 걸리면 더 오래 기다려야 하는 쪽을 알려 주고, 막힌 시도는 기록하지 않는다. */
  SendPermit reserveSend(String email, Instant now);

  /** 새 인증번호를 저장한다. 이전 인증번호와 시도 횟수는 무효가 된다. */
  void saveCode(String email, String codeHash, Instant expiresAt);

  /** 직전 {@link #reserveSend} 예약과 저장한 인증번호를 되돌린다 (메일 발송 실패 시). 예약이 없으면 아무 일도 하지 않는다. */
  void cancelSend(String email);

  /**
   * 인증번호를 확인한다. 맞으면 인증번호가 즉시 지워져(1회용) 다시 쓸 수 없다. 틀리면 시도 횟수가 올라간다.
   *
   * @param maxAttempts 이 횟수만큼 틀리면 이후에는 맞는 인증번호도 {@link ConfirmOutcome#ATTEMPTS_EXCEEDED}
   */
  ConfirmOutcome confirmCode(String email, String codeHash, Instant now, int maxAttempts);

  /** 인증 완료 토큰을 저장한다. 토큰은 해당 이메일에서만 유효하다. */
  void saveToken(String tokenHash, String email, Instant expiresAt);

  /** 토큰이 있고, 그 이메일의 것이며, 만료 전인지 확인한다. 읽기 전용이라 토큰을 소비하지 않는다. */
  boolean hasValidToken(String tokenHash, String email, Instant now);

  /** 토큰을 지운다 (가입이 커밋된 뒤). 없으면 아무 일도 하지 않는다. */
  void deleteToken(String tokenHash);

  /** 발송 예약 결과. 막혔을 때 {@code retryAfterSeconds}는 다시 시도할 수 있기까지의 남은 초(1 이상), 허용이면 0. */
  record SendPermit(Status status, long retryAfterSeconds) {

    public enum Status {
      ALLOWED,
      /** 직전 발송으로부터 재발송 간격이 지나지 않았다. */
      COOLDOWN,
      /** 최근 1시간 발송 횟수를 다 썼다. */
      HOURLY_LIMIT
    }

    public static SendPermit allowed() {
      return new SendPermit(Status.ALLOWED, 0);
    }

    public boolean isAllowed() {
      return status == Status.ALLOWED;
    }
  }

  /** 인증번호 확인 결과. */
  enum ConfirmOutcome {
    /** 맞았다. 인증번호는 지워졌다. */
    OK,
    /** 틀렸다. 시도 횟수가 올라갔다. */
    MISMATCH,
    /** 인증번호가 만료됐거나, 발송한 적이 없거나, 이미 썼다. */
    EXPIRED_OR_MISSING,
    /** 틀린 횟수가 한도를 넘었다. 새 인증번호를 받아야 한다. */
    ATTEMPTS_EXCEEDED
  }
}
