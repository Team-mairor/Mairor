package com.mairor.backend.users.support;

import java.time.Instant;
import java.util.Optional;

/**
 * 이메일 인증(가입 이메일 소유 확인, 비밀번호 재설정)의 임시 상태(인증번호, 시도 횟수, 재발송 제한, 인증 토큰) 저장소. 서비스는 이 인터페이스만 보고
 * 구현체({@link InMemoryEmailVerificationStore})를 바꿀 수 있다. 계약은 {@code EmailVerificationStoreContract}로
 * 확인한다. 용도마다 인스턴스를 따로 두어 서로의 인증번호·토큰이 섞이지 않게 한다.
 *
 * <ul>
 *   <li>모든 연산은 이메일(또는 토큰) 단위로 원자적이다.
 *   <li>인증번호와 토큰은 평문이 아니라 해시({@link VerificationHasher})만 받고, 이메일은 정규화한 값이다.
 *   <li>현재 시각은 호출자가 넘긴다.
 *   <li>만료와 "발송 이력 없음"은 구별하지 않는다.
 *   <li>발송 예약마다 <b>세대 값</b>이 붙는다. 인증번호 저장과 발송 취소는 자기 세대에 대해서만 동작해서, 늦게 도착한 요청이 그사이 다른 요청이 저장한 새
 *       인증번호를 지우거나 덮어쓰지 못한다.
 *   <li>이메일마다 유효한 토큰은 하나다. 새 토큰을 저장하면 같은 이메일의 이전 토큰은 무효가 된다.
 * </ul>
 */
public interface EmailVerificationStore {

  /**
   * 인증번호 발송 한 번을 예약한다. 쿨다운과 시간당 한도가 함께 걸리면 더 오래 기다려야 하는 쪽을 알려 주고, 막힌 시도는 기록하지 않는다. 허용되면 이 예약의 세대 값을
   * 돌려준다 (이후 {@link #saveCode}·{@link #cancelSend}에 그대로 넘긴다).
   */
  SendPermit reserveSend(String email, Instant now);

  /**
   * 새 인증번호를 저장한다. 이전 인증번호와 시도 횟수는 무효가 된다. 이미 저장된 인증번호가 {@code generation}보다 <b>새로운</b> 세대의 것이면
   * 무시한다(늦게 도착한 요청이 새 인증번호를 덮어쓰지 못한다).
   *
   * @param generation 이 인증번호를 만든 {@link #reserveSend} 예약의 세대 값
   */
  void saveCode(String email, String codeHash, Instant expiresAt, long generation);

  /**
   * {@code generation} 세대의 {@link #reserveSend} 예약을 되돌린다 (메일 발송 등이 실패했을 때). 그 세대의 발송 기록을 지우고, 저장된
   * 인증번호가 <b>그 세대의 것일 때만</b> 인증번호도 지운다. 그 세대의 예약이 없으면 아무 일도 하지 않는다.
   */
  void cancelSend(String email, long generation);

  /**
   * 인증번호를 확인한다. 맞으면 인증번호가 즉시 지워져(1회용) 다시 쓸 수 없다. 틀리면 시도 횟수가 올라간다.
   *
   * @param maxAttempts 이 횟수만큼 틀리면 이후에는 맞는 인증번호도 {@link ConfirmOutcome#ATTEMPTS_EXCEEDED}
   */
  ConfirmOutcome confirmCode(String email, String codeHash, Instant now, int maxAttempts);

  /**
   * 인증 완료 토큰을 저장한다. 토큰은 해당 이메일에서만 유효하고, 같은 이메일의 이전 토큰은 무효가 된다.
   *
   * @param stamp 호출자가 토큰과 함께 기억해 둘 값. 비밀번호 재설정은 발급 시점의 비밀번호 버전을 넣어, 그 토큰으로 이미 비밀번호를 바꿨는지(재시도인지) 가린다
   */
  void saveToken(String tokenHash, String email, long stamp, Instant expiresAt);

  /** 기억해 둘 값 없이({@code stamp} 0) 토큰을 저장한다. 가입 이메일 인증이 쓴다. */
  default void saveToken(String tokenHash, String email, Instant expiresAt) {
    saveToken(tokenHash, email, 0, expiresAt);
  }

  /** 토큰이 있고, 그 이메일의 것이며, 만료 전인지 확인한다. 읽기 전용이라 토큰을 소비하지 않는다. */
  boolean hasValidToken(String tokenHash, String email, Instant now);

  /**
   * 토큰이 가리키는 이메일과 저장할 때 넘긴 {@code stamp}를 돌려준다. 토큰이 있고 만료 전이며 그 이메일의 <b>현재</b> 토큰일 때만 값이 있다. 읽기
   * 전용이라 토큰을 소비하지 않는다.
   */
  Optional<IssuedToken> findToken(String tokenHash, Instant now);

  /** {@link #findToken}의 이메일만. */
  default Optional<String> findTokenEmail(String tokenHash, Instant now) {
    return findToken(tokenHash, now).map(IssuedToken::email);
  }

  /** 토큰을 지운다 (가입이 커밋된 뒤). 없으면 아무 일도 하지 않는다. */
  void deleteToken(String tokenHash);

  /**
   * 이메일에 남은 토큰과 인증번호(시도 횟수 포함)를 모두 지운다. 발송 기록(쿨다운, 시간당 횟수)은 남긴다: 지우면 제한을 우회할 수 있다. 상태가 없으면 아무 일도 하지
   * 않는다.
   */
  void invalidateAll(String email);

  /**
   * 발송 예약 결과. 막혔을 때 {@code retryAfterSeconds}는 다시 시도할 수 있기까지의 남은 초(1 이상), 허용이면 0. {@code
   * generation}은 허용일 때만 뜻이 있다.
   */
  record SendPermit(Status status, long retryAfterSeconds, long generation) {

    public enum Status {
      ALLOWED,
      /** 직전 발송으로부터 재발송 간격이 지나지 않았다. */
      COOLDOWN,
      /** 최근 1시간 발송 횟수를 다 썼다. */
      HOURLY_LIMIT
    }

    public static SendPermit allowed(long generation) {
      return new SendPermit(Status.ALLOWED, 0, generation);
    }

    public static SendPermit blocked(Status status, long retryAfterSeconds) {
      return new SendPermit(status, retryAfterSeconds, 0);
    }

    public boolean isAllowed() {
      return status == Status.ALLOWED;
    }
  }

  /** 유효한 토큰의 내용. */
  record IssuedToken(String email, long stamp) {}

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
