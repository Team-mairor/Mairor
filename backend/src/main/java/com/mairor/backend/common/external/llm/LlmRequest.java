package com.mairor.backend.common.external.llm;

import java.util.Objects;

/**
 * 영상 하나와 지시문으로 JSON 답을 받는 요청.
 *
 * @param videoUri 모델이 직접 읽는 영상 주소(유튜브 URL)
 * @param prompt 지시문
 * @param responseSchema 답의 형식(Gemini {@code responseSchema} JSON)
 * @param temperature 0~2. 낮을수록 실행마다 비슷하게 답한다
 */
public record LlmRequest(
    String videoUri, String prompt, String responseSchema, double temperature) {

  public LlmRequest {
    Objects.requireNonNull(videoUri, "videoUri");
    Objects.requireNonNull(prompt, "prompt");
    Objects.requireNonNull(responseSchema, "responseSchema");
  }
}
