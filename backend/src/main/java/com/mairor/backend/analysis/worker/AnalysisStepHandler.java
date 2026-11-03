package com.mairor.backend.analysis.worker;

import com.mairor.backend.analysis.entity.ProgressStage;

/**
 * 분석의 한 단계. 빈으로 등록하면 {@link AnalysisJobRunner}가 {@link AnalysisJobRunner#STAGE_ORDER} 순서대로 실행한다. 한
 * 단계에 처리기는 하나만 둔다.
 *
 * <p>처리기는 같은 작업에 다시 불려도 같은 결과를 내야 한다(재시작 복구와 재시도는 처음 단계부터 다시 돈다). 긴 작업(내려받기·외부 호출)을 트랜잭션 안에서 하지
 * 않는다.
 */
public interface AnalysisStepHandler {

  ProgressStage stage();

  /**
   * @throws AnalysisStepException 원인을 분류한 실패
   */
  void run(AnalysisContext context);

  /**
   * 일을 다른 곳(AI 서버)에 맡기고 결과는 나중에 오는 처리기인지. 그렇다면 실행기는 작업을 COMPLETED 로 바꾸지 않고, 콜백이 끝낸다. 마지막 단계에만 쓴다.
   */
  default boolean finishesLater() {
    return false;
  }
}
