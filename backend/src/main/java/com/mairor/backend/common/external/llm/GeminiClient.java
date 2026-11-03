package com.mairor.backend.common.external.llm;

import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * Gemini {@code generateContent}로 영상(유튜브 URL)을 넣고 JSON 답을 받는다. GMS 도 같은 형식이라 주소·키만 다르다.
 *
 * <p>429·5xx·연결 실패·시간 초과는 {@code maxAttempts}까지 다시 부른다. 그 밖의 4xx 는 바로 실패한다. 200 이어도 답이 잘렸으면({@code
 * finishReason}이 {@code STOP}이 아님) 쓸 수 없는 답으로 본다.
 */
@Component
public class GeminiClient implements LlmClient {

  /** 재시도 사이의 대기. 테스트에서 바꾼다. */
  @FunctionalInterface
  interface Sleeper {
    void sleep(Duration duration) throws InterruptedException;
  }

  private static final Logger log = LoggerFactory.getLogger(GeminiClient.class);

  private final GeminiProperties properties;
  private final RestClient restClient;
  private final ObjectMapper objectMapper;
  private final Sleeper sleeper;

  @Autowired
  public GeminiClient(
      GeminiProperties properties, RestClient.Builder builder, ObjectMapper objectMapper) {
    this(
        properties,
        builder.requestFactory(requestFactory(properties)).build(),
        objectMapper,
        duration -> Thread.sleep(duration));
  }

  GeminiClient(
      GeminiProperties properties,
      RestClient restClient,
      ObjectMapper objectMapper,
      Sleeper sleeper) {
    this.properties = properties;
    this.restClient = restClient;
    this.objectMapper = objectMapper;
    this.sleeper = sleeper;
  }

  private static JdkClientHttpRequestFactory requestFactory(GeminiProperties properties) {
    HttpClient httpClient =
        HttpClient.newBuilder().connectTimeout(properties.connectTimeout()).build();
    JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(httpClient);
    factory.setReadTimeout(properties.readTimeout());
    return factory;
  }

  @Override
  public LlmResult generate(LlmRequest request) {
    String provider = properties.provider();
    String model = properties.model();
    if (!properties.configured()) {
      throw new LlmException(
          LlmException.Kind.NOT_CONFIGURED,
          "Gemini 키(app.llm.gemini.api-key)가 없습니다.",
          null,
          provider,
          model,
          null);
    }
    String body = requestBody(request);
    String url = properties.baseUrl() + "/v1beta/models/" + model + ":generateContent";

    LlmException last = null;
    for (int attempt = 1; attempt <= properties.maxAttempts(); attempt++) {
      if (attempt > 1) {
        Duration wait = properties.retryBackoff().multipliedBy(1L << (attempt - 2));
        log.warn("Gemini 재시도 attempt={} wait={} 이전 실패={}", attempt, wait, last.getMessage());
        sleep(wait, last);
      }
      RawResponse response;
      try {
        response = post(url, body);
      } catch (RestClientException e) {
        last =
            new LlmException(
                LlmException.Kind.UNAVAILABLE,
                "Gemini 에 연결하지 못했습니다: " + e.getMessage(),
                null,
                provider,
                model,
                e);
        continue;
      }
      if (response.status() == 429 || response.status() >= 500) {
        last =
            new LlmException(
                LlmException.Kind.UNAVAILABLE,
                "Gemini 가 일시적으로 응답하지 않습니다(HTTP " + response.status() + ").",
                response.status(),
                provider,
                model,
                null);
        continue;
      }
      if (response.status() != 200) {
        throw new LlmException(
            LlmException.Kind.REJECTED,
            "Gemini 가 요청을 거절했습니다(HTTP " + response.status() + "): " + brief(response.body()),
            response.status(),
            provider,
            model,
            null);
      }
      return parse(response.body(), provider, model, attempt);
    }
    throw last;
  }

  private String requestBody(LlmRequest request) {
    JsonNode schema;
    try {
      schema = objectMapper.readTree(request.responseSchema());
    } catch (JacksonException e) {
      throw new IllegalArgumentException("응답 형식이 JSON 이 아닙니다.", e);
    }
    Map<String, Object> body =
        Map.of(
            "contents",
            List.of(
                Map.of(
                    "parts",
                    List.of(
                        Map.of("fileData", Map.of("fileUri", request.videoUri())),
                        Map.of("text", request.prompt())))),
            "generationConfig",
            Map.of(
                "responseMimeType",
                "application/json",
                "responseSchema",
                schema,
                "temperature",
                request.temperature()));
    return objectMapper.writeValueAsString(body);
  }

  private RawResponse post(String url, String body) {
    return restClient
        .post()
        .uri(url)
        .header(properties.apiKeyHeader(), properties.apiKey())
        .contentType(MediaType.APPLICATION_JSON)
        .body(body)
        .exchange(
            (req, res) ->
                new RawResponse(
                    res.getStatusCode().value(),
                    new String(res.getBody().readAllBytes(), StandardCharsets.UTF_8)));
  }

  private LlmResult parse(String body, String provider, String model, int attempts) {
    JsonNode root;
    try {
      root = objectMapper.readTree(body);
    } catch (JacksonException e) {
      throw invalid("Gemini 응답이 JSON 이 아닙니다.", provider, model, e);
    }
    JsonNode candidate = root.path("candidates").path(0);
    if (candidate.isMissingNode()) {
      String blocked = root.path("promptFeedback").path("blockReason").asString("");
      throw invalid(
          "Gemini 가 답을 내지 않았습니다" + (blocked.isEmpty() ? "." : "(차단: " + blocked + ")."),
          provider,
          model,
          null);
    }
    String finishReason = candidate.path("finishReason").asString("");
    if (!"STOP".equals(finishReason)) {
      throw invalid(
          "Gemini 답이 끝나지 않았습니다(finishReason=" + finishReason + ").", provider, model, null);
    }
    StringBuilder text = new StringBuilder();
    for (JsonNode part : candidate.path("content").path("parts")) {
      text.append(part.path("text").asString(""));
    }
    if (text.isEmpty()) {
      throw invalid("Gemini 답이 비었습니다.", provider, model, null);
    }
    JsonNode usage = root.path("usageMetadata");
    Integer input = intOrNull(usage.path("promptTokenCount"));
    Integer candidates = intOrNull(usage.path("candidatesTokenCount"));
    Integer thoughts = intOrNull(usage.path("thoughtsTokenCount"));
    Integer output =
        candidates == null && thoughts == null
            ? null
            : (candidates == null ? 0 : candidates) + (thoughts == null ? 0 : thoughts);
    return new LlmResult(provider, model, text.toString(), input, output, attempts);
  }

  private void sleep(Duration wait, LlmException last) {
    try {
      sleeper.sleep(wait);
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw last;
    }
  }

  private static LlmException invalid(
      String message, String provider, String model, Throwable cause) {
    return new LlmException(
        LlmException.Kind.INVALID_RESPONSE, message, 200, provider, model, cause);
  }

  private static Integer intOrNull(JsonNode node) {
    return node.isNumber() ? node.asInt() : null;
  }

  private static String brief(String body) {
    String oneLine = body == null ? "" : body.replaceAll("\\s+", " ").trim();
    return oneLine.length() > 300 ? oneLine.substring(0, 300) + "…" : oneLine;
  }

  private record RawResponse(int status, String body) {}
}
