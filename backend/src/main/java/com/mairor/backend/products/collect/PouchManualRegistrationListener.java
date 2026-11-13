package com.mairor.backend.products.collect;

import com.mairor.backend.pouch.event.PouchItemRegisteredManually;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

/** 직접 입력 등록이 커밋된 뒤 수집 요청을 만든다. 실패해도 등록은 이미 끝났으므로 로그만 남긴다. */
@Component
public class PouchManualRegistrationListener {

  private static final Logger log = LoggerFactory.getLogger(PouchManualRegistrationListener.class);

  private final CollectRequestIntake intake;

  public PouchManualRegistrationListener(CollectRequestIntake intake) {
    this.intake = intake;
  }

  @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
  public void afterRegistered(PouchItemRegisteredManually event) {
    try {
      CollectRequestIntake.Intake result = intake.requestFor(event.userId(), event.pouchItemId());
      log.info(
          "수집 요청 접수: item={} outcome={} request={}",
          event.pouchItemId(),
          result.outcome(),
          result.requestId());
    } catch (RuntimeException e) {
      log.warn("수집 요청을 만들지 못했다(등록은 성공): item={}", event.pouchItemId(), e);
    }
  }
}
