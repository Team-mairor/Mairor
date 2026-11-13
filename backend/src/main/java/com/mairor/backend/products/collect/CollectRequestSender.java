package com.mairor.backend.products.collect;

import com.mairor.backend.products.entity.CatalogCollectRequest;
import com.mairor.backend.products.entity.CollectRequestStatus;
import com.mairor.backend.products.repository.CatalogCollectRequestRepository;
import java.time.Clock;
import java.util.Optional;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * QUEUED 요청을 수집 큐에 보낸다. 요청 행을 잠그고 보내서 두 곳이 같은 요청을 겹쳐 보내지 않는다. 보낸 뒤 DB 반영이 실패해 다시 보내도 워커가 jobId 로 한
 * 번만 반영한다.
 *
 * <p>보내기에 실패하면 QUEUED 로 남겨 주기 작업({@link CollectRequestSendSweeper})이 다시 보낸다. {@code
 * catalog.collect.max-send-attempts}번 실패하면 FAILED({@code SEND_FAILED})로 끝낸다.
 */
@Service
public class CollectRequestSender {

  static final String SEND_FAILED = "SEND_FAILED";

  private static final Logger log = LoggerFactory.getLogger(CollectRequestSender.class);

  private final CatalogCollectRequestRepository requests;
  private final CollectJobQueue queue;
  private final CatalogCollectProperties properties;
  private final Clock clock;

  public CollectRequestSender(
      CatalogCollectRequestRepository requests,
      CollectJobQueue queue,
      CatalogCollectProperties properties,
      Clock clock) {
    this.requests = requests;
    this.queue = queue;
    this.properties = properties;
    this.clock = clock;
  }

  /** 보낸 결과. */
  public enum Sent {
    SENT,
    NOT_QUEUED,
    QUEUE_DISABLED,
    RETRY_LATER,
    GAVE_UP
  }

  @Transactional(propagation = Propagation.REQUIRES_NEW)
  public Sent send(UUID requestId) {
    if (!queue.enabled()) {
      return Sent.QUEUE_DISABLED;
    }
    Optional<CatalogCollectRequest> found = requests.findByIdForUpdate(requestId);
    if (found.isEmpty() || found.get().getStatus() != CollectRequestStatus.QUEUED) {
      return Sent.NOT_QUEUED;
    }
    CatalogCollectRequest request = found.get();
    try {
      queue.send(CollectJobMessage.of(request));
    } catch (CollectJobQueue.CollectQueueException e) {
      request.markSendFailed();
      if (request.getSendAttempts() >= properties.maxSendAttempts()) {
        request.finish(CollectRequestStatus.FAILED, SEND_FAILED, clock.instant());
        log.error("수집 요청을 큐에 보내지 못해 끝낸다: request={}", requestId, e);
        return Sent.GAVE_UP;
      }
      log.warn("수집 요청을 큐에 보내지 못했다({}번째): request={}", request.getSendAttempts(), requestId, e);
      return Sent.RETRY_LATER;
    }
    request.markSent(clock.instant());
    return Sent.SENT;
  }
}
