package com.mairor.backend.guides.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.guides.repository.GuideRepository;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.stereotype.Service;

/** 커밋 후 자동 처리와 운영자 재실행을 같은 비동기 경로로 보낸다. */
@Service
public class GuideReferenceLinkReconciliationDispatcher {

  private static final Logger log =
      LoggerFactory.getLogger(GuideReferenceLinkReconciliationDispatcher.class);

  private final TaskExecutor executor;
  private final GuideRepository guides;
  private final GuideStepProductLinkReconciler reconciler;

  GuideReferenceLinkReconciliationDispatcher(
      @Qualifier("guideReferenceTaskExecutor") TaskExecutor executor,
      GuideRepository guides,
      GuideStepProductLinkReconciler reconciler) {
    this.executor = executor;
    this.guides = guides;
    this.reconciler = reconciler;
  }

  /** AI 콜백 뒤 예약 실패는 이미 커밋된 분석 응답에 영향을 주지 않는다. */
  public void scheduleAfterCommit(UUID guideId) {
    try {
      submit(guideId, true);
    } catch (RuntimeException e) {
      log.error("가이드 원본 제품 대조 예약 중 예기치 않은 오류 guideId={}", guideId, e);
    }
  }

  /** 내부 운영 API 의 재대조 요청. 202 는 예약 완료를 뜻하며 처리가 끝났다는 뜻은 아니다. */
  public void requestManualReconciliation(UUID guideId) {
    if (!guides.existsById(guideId)) {
      throw new BusinessException(ErrorCode.NOT_FOUND);
    }
    submit(guideId, false);
  }

  private void submit(UUID guideId, boolean suppressRejection) {
    try {
      executor.execute(
          () -> {
            try {
              int changed = reconciler.reconcile(guideId);
              log.info("가이드 원본 제품 대조 완료 guideId={} changedSteps={}", guideId, changed);
            } catch (RuntimeException e) {
              log.error("가이드 원본 제품 대조 실패 guideId={}", guideId, e);
            }
          });
    } catch (TaskRejectedException e) {
      log.error("가이드 원본 제품 대조 작업 예약 실패 guideId={}", guideId, e);
      if (!suppressRejection) {
        throw new BusinessException(ErrorCode.SERVICE_UNAVAILABLE, "대조 작업 대기열이 가득 찼습니다.");
      }
    }
  }
}
