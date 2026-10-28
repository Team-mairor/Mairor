package com.mairor.backend.users.support;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * 인메모리(Caffeine) 인증 임시 상태 저장소. 이메일(토큰은 해시)마다 {@code compute}로 읽기·판단·쓰기를 한 번에 해서 동시 요청이 경쟁하지 못하게 한다.
 * 만료는 값에 든 시각과 호출자가 넘긴 {@code now}로 판단하고, Caffeine 만료는 메모리 정리용이다.
 *
 * <p>한계: 서버 1대에서만 정확하고, 재시작하면 진행 중인 인증이 사라진다.
 */
public class InMemoryEmailVerificationStore implements EmailVerificationStore {

  /** 시간당 발송 횟수를 세는 시간 창. */
  static final Duration HOURLY_WINDOW = Duration.ofHours(1);

  /** 키가 이 수를 넘으면 오래된 것부터 잊는다 (메모리 상한). */
  private static final long MAX_KEYS = 100_000;

  private record Code(String hash, int attempts, Instant expiresAt) {}

  /** 이메일 하나의 상태: 최근 1시간 발송 시각들(오래된 순)과 현재 유효한 인증번호. */
  private record State(List<Instant> sends, Code code) {
    boolean isEmpty() {
      return sends.isEmpty() && code == null;
    }
  }

  private record Token(String email, Instant expiresAt) {}

  private final Duration resendCooldown;
  private final int hourlyLimit;
  private final Cache<String, State> states;
  private final Cache<String, Token> tokens;

  public InMemoryEmailVerificationStore(Duration resendCooldown, int hourlyLimit) {
    if (resendCooldown.isNegative() || hourlyLimit < 1) {
      throw new IllegalArgumentException("재발송 간격은 0 이상, 시간당 횟수는 1 이상이어야 합니다.");
    }
    this.resendCooldown = resendCooldown;
    this.hourlyLimit = hourlyLimit;
    this.states =
        Caffeine.newBuilder().expireAfterWrite(Duration.ofHours(2)).maximumSize(MAX_KEYS).build();
    this.tokens =
        Caffeine.newBuilder().expireAfterWrite(Duration.ofHours(2)).maximumSize(MAX_KEYS).build();
  }

  @Override
  public SendPermit reserveSend(String email, Instant now) {
    SendPermit[] result = new SendPermit[1];
    states
        .asMap()
        .compute(
            email,
            (key, current) -> {
              List<Instant> sends = recentSends(current, now);
              Code code = current == null ? null : current.code();

              if (sends.size() >= hourlyLimit) {
                Instant free = sends.get(0).plus(HOURLY_WINDOW);
                result[0] = new SendPermit(SendPermit.Status.HOURLY_LIMIT, secondsUntil(free, now));
                return new State(sends, code);
              }
              if (!sends.isEmpty()) {
                Instant free = sends.get(sends.size() - 1).plus(resendCooldown);
                if (now.isBefore(free)) {
                  result[0] = new SendPermit(SendPermit.Status.COOLDOWN, secondsUntil(free, now));
                  return new State(sends, code);
                }
              }
              sends.add(now);
              result[0] = SendPermit.allowed();
              return new State(sends, code);
            });
    return result[0];
  }

  @Override
  public void saveCode(String email, String codeHash, Instant expiresAt) {
    states
        .asMap()
        .compute(
            email,
            (key, current) -> {
              List<Instant> sends = current == null ? new ArrayList<>() : current.sends();
              return new State(sends, new Code(codeHash, 0, expiresAt));
            });
  }

  @Override
  public void cancelSend(String email) {
    states
        .asMap()
        .compute(
            email,
            (key, current) -> {
              if (current == null) {
                return null;
              }
              List<Instant> sends = new ArrayList<>(current.sends());
              if (!sends.isEmpty()) {
                sends.remove(sends.size() - 1);
              }
              State next = new State(sends, null);
              return next.isEmpty() ? null : next;
            });
  }

  @Override
  public ConfirmOutcome confirmCode(String email, String codeHash, Instant now, int maxAttempts) {
    ConfirmOutcome[] result = new ConfirmOutcome[1];
    states
        .asMap()
        .compute(
            email,
            (key, current) -> {
              Code code = current == null ? null : current.code();
              if (code == null || !now.isBefore(code.expiresAt())) {
                result[0] = ConfirmOutcome.EXPIRED_OR_MISSING;
                // 만료된 인증번호는 지운다
                return code == null ? current : withCode(current, null);
              }
              if (code.attempts() >= maxAttempts) {
                result[0] = ConfirmOutcome.ATTEMPTS_EXCEEDED;
                return current;
              }
              if (sameHash(code.hash(), codeHash)) {
                result[0] = ConfirmOutcome.OK;
                return withCode(current, null);
              }
              result[0] = ConfirmOutcome.MISMATCH;
              return withCode(
                  current, new Code(code.hash(), code.attempts() + 1, code.expiresAt()));
            });
    return result[0];
  }

  @Override
  public void saveToken(String tokenHash, String email, Instant expiresAt) {
    tokens.put(tokenHash, new Token(email, expiresAt));
  }

  @Override
  public boolean hasValidToken(String tokenHash, String email, Instant now) {
    Token token = tokens.getIfPresent(tokenHash);
    return token != null && token.email().equals(email) && now.isBefore(token.expiresAt());
  }

  @Override
  public void deleteToken(String tokenHash) {
    tokens.invalidate(tokenHash);
  }

  /** 최근 1시간 안의 발송 시각만 모은 새 목록(오래된 순). */
  private static List<Instant> recentSends(State state, Instant now) {
    List<Instant> recent = new ArrayList<>();
    if (state != null) {
      for (Instant sent : state.sends()) {
        if (now.isBefore(sent.plus(HOURLY_WINDOW))) {
          recent.add(sent);
        }
      }
    }
    return recent;
  }

  private static State withCode(State state, Code code) {
    State next = new State(state.sends(), code);
    return next.isEmpty() ? null : next;
  }

  /** 비교 시간이 내용에 따라 달라지지 않게 한다. */
  private static boolean sameHash(String expected, String actual) {
    return MessageDigest.isEqual(
        expected.getBytes(StandardCharsets.UTF_8), actual.getBytes(StandardCharsets.UTF_8));
  }

  /** 남은 시간을 올림한 초. 항상 1 이상이라 {@code Retry-After: 0}이 나가지 않는다. */
  private static long secondsUntil(Instant end, Instant now) {
    long millis = Duration.between(now, end).toMillis();
    return Math.max(1, (millis + 999) / 1000);
  }
}
