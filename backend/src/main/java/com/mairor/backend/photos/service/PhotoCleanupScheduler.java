package com.mairor.backend.photos.service;

import com.mairor.backend.photos.repository.StoredPhotoRepository;
import java.time.Clock;
import java.time.Duration;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.data.domain.PageRequest;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/** 업로드 원장/정리 대기 행을 조회한다. 연결된 사진의 보관 기한은 도메인 서비스가 별도로 관리한다. */
@Component
@EnableScheduling
@ConditionalOnProperty(
    prefix = "app.photos",
    name = "cleanup-enabled",
    havingValue = "true",
    matchIfMissing = true)
public class PhotoCleanupScheduler {
  private static final Logger log = LoggerFactory.getLogger(PhotoCleanupScheduler.class);
  private final StoredPhotoRepository photos;
  private final PhotoCleanupService cleanup;
  private final PhotoStorageProperties properties;
  private final Clock clock;
  private final PhotoCleanupMetrics metrics;

  public PhotoCleanupScheduler(
      StoredPhotoRepository photos,
      PhotoCleanupService cleanup,
      PhotoStorageProperties properties,
      Clock clock,
      PhotoCleanupMetrics metrics) {
    this.photos = photos;
    this.cleanup = cleanup;
    this.properties = properties;
    this.clock = clock;
    this.metrics = metrics;
  }

  @Scheduled(
      fixedDelayString = "${app.photos.cleanup-interval:1m}",
      initialDelayString = "${app.photos.cleanup-interval:1m}")
  public void sweep() {
    try {
      long overdue = photos.countOverdueCleanup(clock.instant().minus(Duration.ofMinutes(15)));
      metrics.overdue(overdue);
      if (overdue > 0) {
        log.warn("사진 삭제 대기 15분 초과 count={}. 저장소 권한과 삭제 실패 지표를 확인한다", overdue);
      }
      for (UUID id :
          photos.findCleanupCandidates(
              clock.instant(), PageRequest.of(0, properties.cleanupBatchSize()))) {
        try {
          cleanup.cleanup(id);
        } catch (RuntimeException e) {
          log.warn("사진 정리 DB 처리 실패 photoId={}. 다음 주기에 재시도한다", id);
        }
      }
    } catch (RuntimeException e) {
      log.warn("사진 정리 대상 조회 실패. 다음 주기에 재시도한다");
    }
  }
}
