package com.mairor.backend.guides.event;

import com.mairor.backend.guides.service.GuideReferenceLinkReconciliationDispatcher;
import com.mairor.backend.products.collect.CollectRequestFinished;
import com.mairor.backend.products.entity.CatalogCollectRequestGuide;
import com.mairor.backend.products.repository.CatalogCollectRequestGuideRepository;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/**
 * 영상 분석 부족분 수집 요청이 끝나면(상태 상관없음) 그 요청을 기다리던 가이드를 다시 대조한다(S15P31A306-518). 대조로 연결이 좋아지면 가이드의 {@code
 * reference_version}이 올라 추천이 다시 계산된다. 대조 뒤 아직 부족한 것은 같은 경로가 다시 판정하고, 최근에 끝난 요청은 되풀이하지 않는다.
 */
@Component
public class CollectRequestGuideListener {

  private final CatalogCollectRequestGuideRepository waitingSteps;
  private final GuideReferenceLinkReconciliationDispatcher dispatcher;

  public CollectRequestGuideListener(
      CatalogCollectRequestGuideRepository waitingSteps,
      GuideReferenceLinkReconciliationDispatcher dispatcher) {
    this.waitingSteps = waitingSteps;
    this.dispatcher = dispatcher;
  }

  @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
  public void afterFinished(CollectRequestFinished event) {
    Set<UUID> guides = new LinkedHashSet<>();
    for (CatalogCollectRequestGuide step : waitingSteps.findByRequestId(event.requestId())) {
      guides.add(step.getGuideId());
    }
    guides.forEach(dispatcher::scheduleAfterCommit);
  }
}
