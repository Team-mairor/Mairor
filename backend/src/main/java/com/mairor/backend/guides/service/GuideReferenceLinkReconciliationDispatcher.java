package com.mairor.backend.guides.service;

import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.stereotype.Service;

/**
 * AI 콜백 커밋 뒤 가이드 원본 제품 대조를 비동기로 돌린다. 대조가 끝나면 카탈로그에 부족한 제품·호수·색을 수집 요청으로 보낸다 (S15P31A306-518). 수집
 * 요청이 실패해도 대조 결과는 그대로다.
 */
@Service
public class GuideReferenceLinkReconciliationDispatcher {

  private static final Logger log =
      LoggerFactory.getLogger(GuideReferenceLinkReconciliationDispatcher.class);

  private final TaskExecutor executor;
  private final GuideStepProductLinkReconciler reconciler;
  private final GuideCatalogGapCollector gapCollector;

  GuideReferenceLinkReconciliationDispatcher(
      @Qualifier("guideReferenceTaskExecutor") TaskExecutor executor,
      GuideStepProductLinkReconciler reconciler,
      GuideCatalogGapCollector gapCollector) {
    this.executor = executor;
    this.reconciler = reconciler;
    this.gapCollector = gapCollector;
  }

  /** AI 콜백 뒤 예약 실패는 이미 커밋된 분석 응답에 영향을 주지 않는다. */
  public void scheduleAfterCommit(UUID guideId) {
    try {
      executor.execute(
          () -> {
            try {
              int changed = reconciler.reconcile(guideId);
              log.info("가이드 원본 제품 대조 완료 guideId={} changedSteps={}", guideId, changed);
            } catch (RuntimeException e) {
              log.error("가이드 원본 제품 대조 실패 guideId={}", guideId, e);
              return;
            }
            try {
              gapCollector.collect(guideId);
            } catch (RuntimeException e) {
              log.error("가이드 부족분 수집 요청 실패(대조 결과는 그대로) guideId={}", guideId, e);
            }
          });
    } catch (TaskRejectedException e) {
      log.error("가이드 원본 제품 대조 작업 예약 실패 guideId={}", guideId, e);
    } catch (RuntimeException e) {
      log.error("가이드 원본 제품 대조 예약 중 예기치 않은 오류 guideId={}", guideId, e);
    }
  }
}
