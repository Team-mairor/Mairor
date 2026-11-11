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
  /** AI 서버에 가이드 생성을 맡기지 못했다(연결 실패, 5xx · 408 · 429, 202 인데 작업 ID 없음). 잠깐의 문제라 다시 하면 된다. */
  AI_UNAVAILABLE(true, "가이드 생성 서버에 요청하지 못했습니다."),
  /** AI 서버가 요청을 거절했다(형식 400, 너무 큼 413 등 4xx). 같은 입력이면 같은 결과라 재시도해도 실패한다. */
  AI_REQUEST_REJECTED(false, "가이드 생성 요청이 거절되었습니다."),
  /** AI 서버가 쉬운 설명을 만들지 못했다(콜백 {@code GENERATION_FAILED}). */
  AI_GENERATION_FAILED(true, "가이드 설명을 만들지 못했습니다."),
  /** AI 서버의 예기치 않은 오류(콜백 {@code INTERNAL_ERROR}). */
  AI_INTERNAL_ERROR(true, "가이드 생성 중 예기치 않은 오류가 발생했습니다."),
  /**
   * AI 결과가 맡긴 작업과 맞지 않는다(다른 영상, 단계 ID 가 가이드 입력과 다름, 프레임을 보냈는데 영역 없음). 같은 입력이면 같은 결과일 가능성이 높아 사람이
   * 원인을 본다.
   */
  AI_RESULT_MISMATCH(false, "가이드 생성 결과가 요청과 맞지 않습니다."),
  /** AI 콜백이 오지 않았다(AI 재시작으로 작업이 사라졌거나 너무 오래 걸림). */
  ANALYSIS_TIMEOUT(true, "분석 시간이 초과되었습니다."),
  /** 쓸 수 있는 단계가 하나도 없다(메이크업 영상이 아니거나 모든 단계가 틀림). API 명세 VIDEO-002. */
  NO_VALID_STEPS(false, "영상에서 따라 할 수 있는 메이크업 단계를 찾지 못했습니다."),
  /** YouTube 가 노트북의 영상 받기를 거절했다(봇 차단 등). 우회하지 않으므로 다시 해도 같다(S15P31A306-357). */
  VIDEO_DOWNLOAD_REJECTED(false, "영상을 받을 수 없습니다."),
  /** 노트북이 정해진 시간 안에 끝내지 못했다(임대가 거듭 만료 — 노트북이 꺼졌거나 멈춤). 노트북이 다시 켜지면 된다. */
  PROCESSOR_TIMEOUT(true, "영상 전처리가 시간 안에 끝나지 않았습니다."),
  /** 노트북이 올린 AI 요청 JSON 이 없거나 형식이 틀렸다(영상 다름 · 단계 ID 겹침 · 프레임 키 없음, S15P31A306-358). 같은 결과물이면 같다. */
  PROCESSOR_OUTPUT_INVALID(false, "영상 전처리 결과를 쓸 수 없습니다."),
  /** 노트북이 알려 온, BE 가 모르는 실패. 재시도 여부는 노트북이 정한다. */
  PROCESSOR_FAILED(true, "영상 전처리에 실패했습니다."),
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
