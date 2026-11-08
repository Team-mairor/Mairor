package com.mairor.backend.analysis.service;

import java.time.ZoneId;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * 회원 분석 요청 설정({@code app.analysis.request}, API-VIDEO-002).
 *
 * @param dailyLimitPerUser 회원 한 명이 하루에 만들 수 있는 새 분석 작업 수. 재사용 · 합류는 세지 않는다. 시연 중 걸리지 않게 넉넉히 둔다(정윤
 *     11.08)
 * @param zone 하루를 나누는 시간대. 명세 3절 "일일 제한 날짜는 Asia/Seoul 기준", 0시에 초기화
 */
@ConfigurationProperties(prefix = "app.analysis.request")
public record AnalysisRequestProperties(
    @DefaultValue("20") int dailyLimitPerUser, @DefaultValue("Asia/Seoul") ZoneId zone) {

  public AnalysisRequestProperties {
    if (dailyLimitPerUser < 1) {
      throw new IllegalArgumentException(
          "app.analysis.request.daily-limit-per-user 는 1 이상이어야 합니다.");
    }
  }
}
