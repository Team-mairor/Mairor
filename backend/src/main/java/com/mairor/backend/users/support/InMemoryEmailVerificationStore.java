package com.mairor.backend.users.support;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.locks.ReentrantLock;

/**
 * 인메모리(Caffeine) 인증 임시 상태 저장소. 이메일마다 {@code compute}로 읽기·판단·쓰기를 한 번에 해서 동시 요청이 경쟁하지 못하게 한다. 만료는 값에
 * 든 시각과 호출자가 넘긴 {@code now}로 판단하고, Caffeine 만료는 메모리 정리용이다.
 *
 * <p>토큰은 해시로 찾는 맵과 이메일로 찾는 맵 두 개로 이루어져 있고(이메일마다 유효한 토큰은 하나), 두 맵을 함께 고치는 연산은 하나의 잠금으로 묶는다. 두 맵은 크기
 * 제한으로 따로 퇴거될 수 있어서, 토큰은 <b>두 맵이 서로를 가리킬 때만</b> 유효로 본다. 한쪽만 남은 항목은 무효다.
 *
 * <p>한계: 서버 1대에서만 정확하고, 재시작하면 진행 중인 인증이 사라진다. 크기 제한을 넘으면 Caffeine 이 정한 항목이 퇴거되며, 가장 오래된 항목이라는 보장은
 * 없다.
 */
public class InMemoryEmailVerificationStore implements EmailVerificationStore {

  /** 시간당 발송 횟수를 세는 시간 창. */
  static final Duration HOURLY_WINDOW = Duration.ofHours(1);

  /** 키가 이 수를 넘으면 일부 항목부터 잊는다 (메모리 상한). */
  private static final long DEFAULT_MAX_KEYS = 100_000;

  /** 발송 한 번의 기록. 취소가 자기 세대의 기록만 지우도록 세대 값을 함께 둔다. */
  private record Send(Instant at, long generation) {}

  private record Code(String hash, int attempts, Instant expiresAt, long generation) {}

  /** 이메일 하나의 상태: 최근 1시간 발송 기록(오래된 순)과 현재 유효한 인증번호. */
  private record State(List<Send> sends, Code code) {
    boolean isEmpty() {
      return sends.isEmpty() && code == null;
    }
  }

  private record Token(String email, long stamp, Instant expiresAt) {}

  private final Duration resendCooldown;
  private final int hourlyLimit;
  private final AtomicLong generations = new AtomicLong();
  private final Cache<String, State> states;

  /** 토큰 두 맵을 함께 고치는 연산의 잠금. 짧은 메모리 연산만 하므로 오래 잡히지 않는다. */
  private final ReentrantLock tokenLock = new ReentrantLock();

  /** 토큰 해시 → 토큰. */
  private final Cache<String, Token> tokens;

  /** 이메일 → 그 이메일의 현재 토큰 해시. */
  private final Cache<String, String> tokenByEmail;

  public InMemoryEmailVerificationStore(Duration resendCooldown, int hourlyLimit) {
    this(resendCooldown, hourlyLimit, DEFAULT_MAX_KEYS);
  }

  InMemoryEmailVerificationStore(Duration resendCooldown, int hourlyLimit, long maxKeys) {
    if (resendCooldown.isNegative() || hourlyLimit < 1) {
      throw new IllegalArgumentException("재발송 간격은 0 이상, 시간당 횟수는 1 이상이어야 합니다.");
    }
    this.resendCooldown = resendCooldown;
    this.hourlyLimit = hourlyLimit;
    this.states =
        Caffeine.newBuilder().expireAfterWrite(Duration.ofHours(2)).maximumSize(maxKeys).build();
    this.tokens =
        Caffeine.newBuilder().expireAfterWrite(Duration.ofHours(2)).maximumSize(maxKeys).build();
    this.tokenByEmail =
        Caffeine.newBuilder().expireAfterWrite(Duration.ofHours(2)).maximumSize(maxKeys).build();
  }

  @Override
  public SendPermit reserveSend(String email, Instant now) {
    SendPermit[] result = new SendPermit[1];
    states
        .asMap()
        .compute(
            email,
            (key, current) -> {
              List<Send> sends = recentSends(current, now);
              Code code = current == null ? null : current.code();

              if (sends.size() >= hourlyLimit) {
                Instant free = sends.get(0).at().plus(HOURLY_WINDOW);
                result[0] =
                    SendPermit.blocked(SendPermit.Status.HOURLY_LIMIT, secondsUntil(free, now));
                return new State(sends, code);
              }
              if (!sends.isEmpty()) {
                Instant free = sends.get(sends.size() - 1).at().plus(resendCooldown);
                if (now.isBefore(free)) {
                  result[0] =
                      SendPermit.blocked(SendPermit.Status.COOLDOWN, secondsUntil(free, now));
                  return new State(sends, code);
                }
              }
              long generation = generations.incrementAndGet();
              sends.add(new Send(now, generation));
              result[0] = SendPermit.allowed(generation);
              return new State(sends, code);
            });
    return result[0];
  }

  @Override
  public void saveCode(String email, String codeHash, Instant expiresAt, long generation) {
    states
        .asMap()
        .compute(
            email,
            (key, current) -> {
              if (current != null
                  && current.code() != null
                  && current.code().generation() > generation) {
                // 더 새로운 예약이 이미 인증번호를 저장했다. 늦게 도착한 저장이 덮어쓰지 못한다
                return current;
              }
              List<Send> sends = current == null ? new ArrayList<>() : current.sends();
              return new State(sends, new Code(codeHash, 0, expiresAt, generation));
            });
  }

  @Override
  public void cancelSend(String email, long generation) {
    states
        .asMap()
        .compute(
            email,
            (key, current) -> {
              if (current == null) {
                return null;
              }
              List<Send> sends = new ArrayList<>(current.sends());
              sends.removeIf(send -> send.generation() == generation);
              Code code = current.code();
              if (code != null && code.generation() == generation) {
                code = null;
              }
              State next = new State(sends, code);
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
                  current,
                  new Code(code.hash(), code.attempts() + 1, code.expiresAt(), code.generation()));
            });
    return result[0];
  }

  @Override
  public void saveToken(String tokenHash, String email, long stamp, Instant expiresAt) {
    tokenLock.lock();
    try {
      String previous = tokenByEmail.getIfPresent(email);
      if (previous != null && !previous.equals(tokenHash)) {
        tokens.invalidate(previous);
      }
      tokens.put(tokenHash, new Token(email, stamp, expiresAt));
      tokenByEmail.put(email, tokenHash);
    } finally {
      tokenLock.unlock();
    }
  }

  @Override
  public boolean hasValidToken(String tokenHash, String email, Instant now) {
    return findTokenEmail(tokenHash, now).filter(email::equals).isPresent();
  }

  @Override
  public Optional<IssuedToken> findToken(String tokenHash, Instant now) {
    tokenLock.lock();
    try {
      Token token = tokens.getIfPresent(tokenHash);
      if (token == null || !now.isBefore(token.expiresAt())) {
        return Optional.empty();
      }
      // 이메일 쪽 맵이 이 토큰을 가리킬 때만 유효하다 (교체됐거나 한쪽만 퇴거된 토큰은 무효)
      if (!tokenHash.equals(tokenByEmail.getIfPresent(token.email()))) {
        return Optional.empty();
      }
      return Optional.of(new IssuedToken(token.email(), token.stamp()));
    } finally {
      tokenLock.unlock();
    }
  }

  @Override
  public void deleteToken(String tokenHash) {
    tokenLock.lock();
    try {
      Token token = tokens.getIfPresent(tokenHash);
      tokens.invalidate(tokenHash);
      if (token != null && tokenHash.equals(tokenByEmail.getIfPresent(token.email()))) {
        tokenByEmail.invalidate(token.email());
      }
    } finally {
      tokenLock.unlock();
    }
  }

  @Override
  public void invalidateAll(String email) {
    tokenLock.lock();
    try {
      String tokenHash = tokenByEmail.getIfPresent(email);
      tokenByEmail.invalidate(email);
      if (tokenHash != null) {
        tokens.invalidate(tokenHash);
      }
    } finally {
      tokenLock.unlock();
    }
    // 인증번호만 지우고 발송 기록(쿨다운, 시간당 횟수)은 남긴다
    states.asMap().computeIfPresent(email, (key, current) -> withCode(current, null));
  }

  /** 테스트용: 이메일 쪽 인덱스만 퇴거된 상황을 만든다. 크기 제한에 따른 퇴거는 맵마다 따로 일어난다. */
  void forgetEmailIndex(String email) {
    tokenByEmail.invalidate(email);
  }

  /** 최근 1시간 안의 발송 기록만 모은 새 목록(오래된 순). */
  private static List<Send> recentSends(State state, Instant now) {
    List<Send> recent = new ArrayList<>();
    if (state != null) {
      for (Send sent : state.sends()) {
        if (now.isBefore(sent.at().plus(HOURLY_WINDOW))) {
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
