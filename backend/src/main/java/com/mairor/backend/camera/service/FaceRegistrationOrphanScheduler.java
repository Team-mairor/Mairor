package com.mairor.backend.camera.service;

import com.mairor.backend.camera.repository.FaceRegistrationOrphanRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@EnableScheduling
@ConditionalOnProperty(
    prefix = "app.face-registration",
    name = "orphan-cleanup-enabled",
    havingValue = "true",
    matchIfMissing = true)
public class FaceRegistrationOrphanScheduler {
  private static final Logger log = LoggerFactory.getLogger(FaceRegistrationOrphanScheduler.class);
  private final FaceRegistrationOrphanRepository orphans;
  private final FaceRegistrationLifecycleService lifecycle;
  private final FaceRegistrationProperties properties;

  public FaceRegistrationOrphanScheduler(
      FaceRegistrationOrphanRepository orphans,
      FaceRegistrationLifecycleService lifecycle,
      FaceRegistrationProperties properties) {
    this.orphans = orphans;
    this.lifecycle = lifecycle;
    this.properties = properties;
  }

  @Scheduled(
      fixedDelayString = "${app.face-registration.cleanup-interval:1m}",
      initialDelayString = "${app.face-registration.cleanup-interval:1m}")
  public void sweep() {
    try {
      for (var orphan : orphans.findMissingSessions(properties.cleanupBatchSize())) {
        try {
          lifecycle.discardIfSessionMissing(orphan.userId(), orphan.registrationId());
        } catch (RuntimeException e) {
          log.warn("미연결 얼굴 등록 정리를 다음 주기에 재시도한다 registrationId={}", orphan.registrationId());
        }
      }
    } catch (RuntimeException e) {
      log.warn("미연결 얼굴 등록 정리 대상 조회 실패. 다음 주기에 재시도한다");
    }
  }
}
