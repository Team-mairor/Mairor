package com.mairor.backend.products.collect;

/** 수집 작업을 큐에 넣는다. 운영은 SQS, 큐 주소가 없으면 보내지 않는다. */
public interface CollectJobQueue {

  /** 큐가 설정됐는가. 아니면 요청은 QUEUED 로 남는다. */
  boolean enabled();

  /**
   * @throws CollectQueueException 보내지 못했으면. 요청은 QUEUED 로 남아 다시 보낸다
   */
  void send(CollectJobMessage message);

  class CollectQueueException extends RuntimeException {
    public CollectQueueException(String message, Throwable cause) {
      super(message, cause);
    }
  }
}
