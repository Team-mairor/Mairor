package com.mairor.backend.guides.event;

import com.mairor.backend.guides.service.GuideReferenceLinkReconciliationDispatcher;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/** 가이드와 분석 완료가 커밋된 다음 비동기 대조를 예약한다. */
@Component
public class ReferenceProductReconciliationListener {

  private final GuideReferenceLinkReconciliationDispatcher dispatcher;

  public ReferenceProductReconciliationListener(
      GuideReferenceLinkReconciliationDispatcher dispatcher) {
    this.dispatcher = dispatcher;
  }

  @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
  public void afterGuideCommitted(ReferenceProductReconciliationRequested event) {
    dispatcher.scheduleAfterCommit(event.guideId());
  }
}
