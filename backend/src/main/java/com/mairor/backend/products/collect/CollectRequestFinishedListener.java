package com.mairor.backend.products.collect;

import com.mairor.backend.products.entity.CatalogCollectRequestUser;
import com.mairor.backend.products.entity.CollectRequestStatus;
import com.mairor.backend.products.repository.CatalogCollectRequestUserRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/**
 * 해결된 수집 요청이 커밋되면 요청한 회원마다 파우치 항목 자동 연결을 판정한다. 회원마다 따로 처리해 한 회원의 실패가 다른 회원에게 번지지 않는다. 연결하지 못해도 항목은
 * 직접 입력 그대로 남는다.
 */
@Component
public class CollectRequestFinishedListener {

  private static final Logger log = LoggerFactory.getLogger(CollectRequestFinishedListener.class);

  private final CatalogCollectRequestUserRepository requesters;
  private final CollectPouchLinker linker;

  public CollectRequestFinishedListener(
      CatalogCollectRequestUserRepository requesters, CollectPouchLinker linker) {
    this.requesters = requesters;
    this.linker = linker;
  }

  @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
  public void afterFinished(CollectRequestFinished event) {
    if (event.status() != CollectRequestStatus.RESOLVED) {
      return;
    }
    for (CatalogCollectRequestUser requester : requesters.findByRequestId(event.requestId())) {
      try {
        String result = linker.link(requester.getId());
        log.info(
            "수집 요청 자동 연결: request={} item={} result={}",
            event.requestId(),
            requester.getPouchItemId(),
            result);
      } catch (RuntimeException e) {
        log.warn(
            "수집 요청 자동 연결 실패(항목은 그대로): request={} item={}",
            event.requestId(),
            requester.getPouchItemId(),
            e);
      }
    }
  }
}
