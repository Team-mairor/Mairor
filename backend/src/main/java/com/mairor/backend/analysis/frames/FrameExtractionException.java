package com.mairor.backend.analysis.frames;

/** ffmpeg 프레임 추출 실패(실행 실패·시간 초과·장수 불일치). */
public class FrameExtractionException extends RuntimeException {

  public FrameExtractionException(String message, Throwable cause) {
    super(message, cause);
  }
}
