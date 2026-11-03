package com.mairor.backend.common.external.llm;

/** 영상을 보고 정해진 JSON 형식으로 답하는 LLM 호출. 지금 구현은 {@link GeminiClient} 하나다. */
public interface LlmClient {

  /**
   * @throws LlmException 호출 실패. {@link LlmException#kind()}로 원인을 나눈다
   */
  LlmResult generate(LlmRequest request);
}
