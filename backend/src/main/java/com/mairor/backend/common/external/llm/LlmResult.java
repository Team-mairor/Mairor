package com.mairor.backend.common.external.llm;

/**
 * LLM 답.
 *
 * @param provider 호출한 곳({@code GMS} | {@code GOOGLE})
 * @param model 모델 이름
 * @param text 모델이 낸 답(JSON 문자열)
 * @param inputTokens 입력 토큰. 응답에 없으면 null
 * @param outputTokens 출력 토큰(생각 토큰 포함, 비용 계산용). 응답에 없으면 null
 * @param attempts 재시도를 포함한 호출 횟수
 */
public record LlmResult(
    String provider,
    String model,
    String text,
    Integer inputTokens,
    Integer outputTokens,
    int attempts) {}
