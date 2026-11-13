package com.mairor.backend.products.collect;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/** 새 요청이 커밋되면 바로 큐에 보낸다. 실패하면 QUEUED 로 남고 주기 작업이 다시 보낸다. */
@Component
public class CollectRequestQueuedListener {

  private static final Logger log = LoggerFactory.getLogger(CollectRequestQueuedListener.class);

  private final CollectRequestSender sender;

  public CollectRequestQueuedListener(CollectRequestSender sender) {
    this.sender = sender;
  }

  @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
  public void afterQueued(CollectRequestQueued event) {
    try {
      sender.send(event.requestId());
    } catch (RuntimeException e) {
      log.warn("수집 요청을 바로 보내지 못했다. 주기 작업이 다시 보낸다: request={}", event.requestId(), e);
    }
  }
}
