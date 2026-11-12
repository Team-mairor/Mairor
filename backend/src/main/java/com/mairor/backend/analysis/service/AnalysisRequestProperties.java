package com.mairor.backend.analysis.service;

import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.entity.AnalysisStatus;
import java.time.ZoneId;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * 회원 분석 요청 설정({@code app.analysis.request}, API-VIDEO-002).
 *
 * @param dailyLimitPerUser 회원 한 명이 하루에 만들 수 있는 새 분석 작업 수. 재사용 · 합류는 세지 않는다. 시연 중 걸리지 않게 넉넉히 둔다(정윤
 *     11.08)
 * @param zone 하루를 나누는 시간대. 명세 3절 "일일 제한 날짜는 Asia/Seoul 기준", 0시에 초기화
 * @param maxAttempts 작업 하나를 처음 포함해 몇 번까지 돌릴 수 있는가(API-VIDEO-006 재시도). 같은 원인이 되풀이되는 작업이 단계 추출 · 가이드
 *     생성 비용을 계속 쓰지 않게 막는다
 */
@ConfigurationProperties(prefix = "app.analysis.request")
public record AnalysisRequestProperties(
    @DefaultValue("20") int dailyLimitPerUser,
    @DefaultValue("Asia/Seoul") ZoneId zone,
    @DefaultValue("3") int maxAttempts) {

  public AnalysisRequestProperties {
    if (dailyLimitPerUser < 1) {
      throw new IllegalArgumentException(
          "app.analysis.request.daily-limit-per-user 는 1 이상이어야 합니다.");
    }
    if (maxAttempts < 1) {
      throw new IllegalArgumentException("app.analysis.request.max-attempts 는 1 이상이어야 합니다.");
    }
  }

  /** 회원이 이 작업을 다시 시도할 수 있는가: 재시도할 수 있는 실패이고 시도 횟수 상한 전이다. 상태 응답의 {@code retryable}도 이 값이다. */
  public boolean canRetry(AnalysisJob job) {
    return job.getStatus() == AnalysisStatus.FAILED
        && job.isRetryable()
        && job.getAttempt() < maxAttempts;
  }
}
