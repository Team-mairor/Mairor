package com.mairor.backend.analysis.entity;

/**
 * 분석 실패 원인. 이름이 그대로 {@code analysis_jobs.failure_code}와 API 의 {@code failureCode}가 된다. 재시도해도 같은 결과가
 * 나오는 원인은 {@code retryable=false}다(API 명세 v2: FAILED 응답의 retryable 로 재시도 버튼을 보일지 정한다).
 *
 * <p>다음 단계 티켓(단계 추출·프레임·AI 요청)이 코드를 더한다.
 */
public enum AnalysisFailureCode {
  /** 분석할 영상 파일이 저장소에 없다(운영자가 올리지 않았거나 키가 틀림). */
  SOURCE_NOT_FOUND(false, "분석할 영상 파일을 찾을 수 없습니다."),
  /** 영상 파일을 해석할 수 없다(영상 스트림 없음, 손상). */
  SOURCE_UNREADABLE(false, "영상 파일을 읽을 수 없습니다."),
  /** 저장소에 일시적으로 닿지 못했다. */
  STORAGE_UNAVAILABLE(true, "저장소에 일시적으로 접근하지 못했습니다."),
  /** 단계 추출 LLM(Gemini)을 부르지 못했다(키 없음, 거절, 재시도를 다 쓴 429·5xx·시간 초과). */
  LLM_UNAVAILABLE(true, "영상 분석 모델을 부르지 못했습니다."),
  /** LLM 이 쓸 수 없는 답을 냈다(JSON 아님, 잘림, 차단). 다시 부르면 대개 통과한다. */
  LLM_INVALID_RESPONSE(true, "영상 분석 모델의 답을 쓸 수 없습니다."),
  /** ffmpeg 로 프레임을 뽑지 못했다(실행 실패·시간 초과·장수 불일치). 같은 파일이면 같은 결과다. */
  FRAME_EXTRACTION_FAILED(false, "영상에서 프레임을 뽑지 못했습니다."),
  /** 쓸 수 있는 단계가 하나도 없다(메이크업 영상이 아니거나 모든 단계가 틀림). API 명세 VIDEO-002. */
  NO_VALID_STEPS(false, "영상에서 따라 할 수 있는 메이크업 단계를 찾지 못했습니다."),
  /** 예기치 않은 오류. */
  INTERNAL_ERROR(true, "분석 중 예기치 않은 오류가 발생했습니다.");

  private final boolean retryable;
  private final String defaultMessage;

  AnalysisFailureCode(boolean retryable, String defaultMessage) {
    this.retryable = retryable;
    this.defaultMessage = defaultMessage;
  }

  public boolean retryable() {
    return retryable;
  }

  public String defaultMessage() {
    return defaultMessage;
  }
}
