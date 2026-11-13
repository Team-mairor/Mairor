package com.mairor.backend.products.collect;

import com.mairor.backend.products.repository.CatalogCollectRequestRepository;
import java.time.Clock;
import java.time.Duration;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 커밋 직후 보내지 못하고 남은 QUEUED 요청을 다시 보낸다. 분석 작업 감시처럼 worker 프로파일에서만 돈다. 겹쳐 돌아도 보내기가 요청 행을 잠가 같은 요청을 두 번
 * 보내지 않는다.
 *
 * <p>방금 넣은 요청은 커밋 직후 보내기가 처리하므로 {@link #GRACE} 보다 오래된 것만 본다.
 */
@Component
@Profile("worker")
class CollectRequestSendSweeper {

  static final Duration GRACE = Duration.ofSeconds(30);
  static final int BATCH = 50;

  private static final Logger log = LoggerFactory.getLogger(CollectRequestSendSweeper.class);

  private final CatalogCollectRequestRepository requests;
  private final CollectRequestSender sender;
  private final Clock clock;

  CollectRequestSendSweeper(
      CatalogCollectRequestRepository requests, CollectRequestSender sender, Clock clock) {
    this.requests = requests;
    this.sender = sender;
    this.clock = clock;
  }

  @Scheduled(
      fixedDelayString = "${catalog.collect.send-interval:60s}",
      initialDelayString = "${catalog.collect.send-interval:60s}")
  void sweep() {
    try {
      for (UUID id : requests.findQueuedIdsBefore(clock.instant().minus(GRACE), BATCH)) {
        sender.send(id);
      }
    } catch (RuntimeException e) {
      log.warn("남은 수집 요청을 다시 보내지 못했다.", e);
    }
  }
}
