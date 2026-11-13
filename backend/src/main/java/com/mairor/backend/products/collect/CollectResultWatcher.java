package com.mairor.backend.products.collect;

import com.mairor.backend.products.repository.CatalogCollectRequestRepository;
import java.time.Clock;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 큐에 보낸 뒤 {@code catalog.collect.result-timeout} 안에 워커 결과가 없는 요청을 FAILED 로 끝낸다. 워커가 결과도 알리지 못하고 실패
 * 큐로 넘어간 작업이 영원히 진행 중으로 남지 않게 한다. worker 프로파일에서만 돌고, 요청 행을 잠가 결과 반영과 겹치지 않는다.
 */
@Component
@Profile("worker")
class CollectResultWatcher {

  static final int BATCH = 50;

  private static final Logger log = LoggerFactory.getLogger(CollectResultWatcher.class);

  private final CatalogCollectRequestRepository requests;
  private final CollectResultService results;
  private final CatalogCollectProperties properties;
  private final Clock clock;

  CollectResultWatcher(
      CatalogCollectRequestRepository requests,
      CollectResultService results,
      CatalogCollectProperties properties,
      Clock clock) {
    this.requests = requests;
    this.results = results;
    this.properties = properties;
    this.clock = clock;
  }

  @Scheduled(
      fixedDelayString = "${catalog.collect.watch-interval:5m}",
      initialDelayString = "${catalog.collect.watch-interval:5m}")
  void check() {
    try {
      for (UUID id :
          requests.findSentIdsBefore(clock.instant().minus(properties.resultTimeout()), BATCH)) {
        results.timeOut(id);
      }
    } catch (RuntimeException e) {
      log.warn("결과가 오지 않은 수집 요청 정리에 실패했다.", e);
    }
  }
}
