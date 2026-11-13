package com.mairor.backend.maintenance;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * 하루 한 번 도는 운영 정리 작업 설정({@code app.maintenance}, S15P31A306-407). worker 에서만 돈다.
 *
 * @param jobFilesKeep 작업이 끝나고 노트북 작업 파일(프레임 · 요청 JSON)을 남겨 두는 기간
 * @param jobFilesLookback 지울 작업을 찾는 끝난 시각의 창(이만큼 전 ~ {@code jobFilesKeep} 전). 매일 돌므로 그보다 오래된 작업은 이미
 *     지웠다
 * @param metaRefreshAfter 영상 메타를 다시 받는 간격. YouTube 정책(ADR-002)은 30일 안
 * @param metaRefreshBatch 한 번에 다시 받는 영상 수
 */
@ConfigurationProperties(prefix = "app.maintenance")
public record MaintenanceProperties(
    @DefaultValue("7d") Duration jobFilesKeep,
    @DefaultValue("30d") Duration jobFilesLookback,
    @DefaultValue("25d") Duration metaRefreshAfter,
    @DefaultValue("200") int metaRefreshBatch) {

  public MaintenanceProperties {
    if (jobFilesKeep.isNegative() || jobFilesKeep.isZero()) {
      throw new IllegalArgumentException("app.maintenance.job-files-keep 은 0 보다 커야 합니다.");
    }
    if (jobFilesLookback.compareTo(jobFilesKeep) <= 0) {
      throw new IllegalArgumentException(
          "app.maintenance.job-files-lookback 은 job-files-keep 보다 길어야 합니다.");
    }
    if (metaRefreshAfter.isNegative() || metaRefreshAfter.isZero()) {
      throw new IllegalArgumentException("app.maintenance.meta-refresh-after 는 0 보다 커야 합니다.");
    }
    if (metaRefreshBatch < 1) {
      throw new IllegalArgumentException("app.maintenance.meta-refresh-batch 는 1 이상이어야 합니다.");
    }
  }
}
