package com.mairor.backend.users.support;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * 로그인 시도 제한 설정 ({@code app.login.*}).
 *
 * @param maxFailures 이메일 하나에서 이 횟수만큼 실패하면 잠근다. 진행 중인 시도도 이 수에 포함돼 동시에 이보다 많이 시도할 수 없다
 * @param lockDuration 잠금 시간
 * @param attemptTtl 마지막 시도 후 실패 횟수를 기억하는 시간
 * @param maxEntries 기억하는 이메일 상태의 최대 개수 (메모리 상한)
 * @param maxConcurrentHashes 동시에 실행할 수 있는 로그인 BCrypt 계산 수 (서버 전체)
 */
@Validated
@ConfigurationProperties(prefix = "app.login")
public record LoginProperties(
    @Min(1) int maxFailures,
    @NotNull Duration lockDuration,
    @NotNull Duration attemptTtl,
    @Min(1) int maxEntries,
    @Min(1) int maxConcurrentHashes) {

  public LoginProperties {
    requirePositive("lock-duration", lockDuration);
    requirePositive("attempt-ttl", attemptTtl);
  }

  private static void requirePositive(String name, Duration value) {
    if (value != null && (value.isZero() || value.isNegative())) {
      throw new IllegalArgumentException("app.login." + name + " 은 0보다 길어야 합니다: " + value);
    }
  }
}
