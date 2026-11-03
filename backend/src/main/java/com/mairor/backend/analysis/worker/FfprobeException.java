package com.mairor.backend.analysis.worker;

/** ffprobe 로 영상 정보를 얻지 못했다(실행 실패·시간 초과·영상 스트림 없음). */
public class FfprobeException extends RuntimeException {

  public FfprobeException(String message) {
    super(message);
  }

  public FfprobeException(String message, Throwable cause) {
    super(message, cause);
  }
}
