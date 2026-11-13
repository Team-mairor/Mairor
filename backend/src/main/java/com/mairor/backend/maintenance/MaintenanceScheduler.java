package com.mairor.backend.maintenance;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 하루 한 번 운영 정리(worker, S15P31A306-407): 끝난 작업의 저장소 파일 정리({@link JobFileCleanup}), 영상 메타 갱신({@link
 * VideoMetaRefresher}). 둘은 서로 기다리지 않는다. 하나가 실패해도 다른 하나는 돈다.
 *
 * <p>worker 는 하나만 뜨므로 두 서버에서 겹쳐 돌지 않는다. 사용자가 적은 새벽(Asia/Seoul)에 돈다.
 */
@Component
@Profile("worker")
class MaintenanceScheduler {

  private static final Logger log = LoggerFactory.getLogger(MaintenanceScheduler.class);

  private final JobFileCleanup jobFiles;
  private final VideoMetaRefresher videoMeta;

  MaintenanceScheduler(JobFileCleanup jobFiles, VideoMetaRefresher videoMeta) {
    this.jobFiles = jobFiles;
    this.videoMeta = videoMeta;
  }

  @Scheduled(cron = "${app.maintenance.cron:0 30 4 * * *}", zone = "Asia/Seoul")
  void runDaily() {
    try {
      jobFiles.run();
    } catch (RuntimeException e) {
      log.error("저장소 정리를 끝내지 못했습니다. 내일 다시 돕니다.", e);
    }
    try {
      videoMeta.run();
    } catch (RuntimeException e) {
      log.error("영상 메타 갱신을 끝내지 못했습니다. 내일 다시 돕니다.", e);
    }
  }
}
