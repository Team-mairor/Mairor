package com.mairor.backend.common.external.ai;

import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

/**
 * AI 서버 가이드 생성 API({@code docs/references/ai-api.md}): 요청 {@code POST /api/v1/guide-jobs}, 상태 조회
 * {@code GET /api/v1/guide-jobs/{jobId}}. 결과는 콜백으로 온다.
 *
 * <p>연결 실패·5xx 는 한 번 더 부른다. 400 은 형식이 틀린 것이라 바로 실패한다. 인증은 없다(AI 서버에 없음).
 */
@Component
public class AiGuideJobClient {

  private static final Logger log = LoggerFactory.getLogger(AiGuideJobClient.class);
  private static final int ATTEMPTS = 2;

  private final AiProperties properties;
  private final RestClient restClient;
  private final ObjectMapper objectMapper;

  @Autowired
  public AiGuideJobClient(
      AiProperties properties, RestClient.Builder builder, ObjectMapper objectMapper) {
    this(properties, builder.requestFactory(requestFactory(properties)).build(), objectMapper);
  }

  AiGuideJobClient(AiProperties properties, RestClient restClient, ObjectMapper objectMapper) {
    this.properties = properties;
    this.restClient = restClient;
    this.objectMapper = objectMapper;
  }

  /**
   * HTTP/1.1 로 고정한다. JDK HttpClient 기본값(HTTP/2)은 {@code http://} 요청에 {@code Upgrade: h2c} 를 붙이는데,
   * AI 서버(uvicorn)는 이 요청의 본문을 읽지 않아 400(본문 없음)으로 거절한다(11.04 운영 E2E).
   */
  private static JdkClientHttpRequestFactory requestFactory(AiProperties properties) {
    JdkClientHttpRequestFactory factory =
        new JdkClientHttpRequestFactory(
            HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(properties.connectTimeout())
                .build());
    factory.setReadTimeout(properties.readTimeout());
    return factory;
  }

  /**
   * 가이드 생성을 요청한다.
   *
   * @param requestJson {@code guide_job_request.v2} 본문
   * @return AI 작업 ID
   * @throws AiServerException 접수되지 않음(재시도까지 실패, 400 등)
   */
  public String submit(String requestJson) {
    String url = properties.baseUrl() + "/api/v1/guide-jobs";
    AiServerException last = null;
    for (int attempt = 1; attempt <= ATTEMPTS; attempt++) {
      Raw response;
      try {
        response =
            restClient
                .post()
                .uri(url)
                .contentType(MediaType.APPLICATION_JSON)
                .body(requestJson)
                .exchange(
                    (req, res) -> raw(res.getStatusCode().value(), res.getBody().readAllBytes()));
      } catch (RestClientException e) {
        last = new AiServerException("AI 서버에 연결하지 못했습니다: " + e.getMessage(), null, e);
        log.warn("AI 가이드 생성 요청 실패 attempt={} {}", attempt, last.getMessage());
        continue;
      }
      if (response.status() == 202 || response.status() == 200) {
        String jobId = readJobId(response.body());
        if (jobId == null) {
          throw new AiServerException(
              "AI 서버 응답에 jobId 가 없습니다: " + brief(response.body()), 202, null);
        }
        return jobId;
      }
      last =
          new AiServerException(
              "AI 서버가 요청을 받지 않았습니다(HTTP " + response.status() + "): " + brief(response.body()),
              response.status(),
              null);
      if (response.status() < 500) {
        throw last;
      }
      log.warn("AI 가이드 생성 요청 실패 attempt={} {}", attempt, last.getMessage());
    }
    throw last;
  }

  /**
   * 작업 상태를 묻는다(콜백을 놓쳤을 때).
   *
   * @return 상태 조회 본문(콜백 칸 + progress 등). AI 서버에 없는 작업(재시작·만료)이면 빈 값
   * @throws AiServerException 연결 실패·5xx
   */
  public Optional<String> find(String aiJobId) {
    Raw response;
    try {
      response =
          restClient
              .get()
              .uri(properties.baseUrl() + "/api/v1/guide-jobs/{jobId}", aiJobId)
              .exchange(
                  (req, res) -> raw(res.getStatusCode().value(), res.getBody().readAllBytes()));
    } catch (RestClientException e) {
      throw new AiServerException("AI 서버에 연결하지 못했습니다: " + e.getMessage(), null, e);
    }
    if (response.status() == 404) {
      return Optional.empty();
    }
    if (response.status() != 200) {
      throw new AiServerException(
          "AI 작업 상태를 받지 못했습니다(HTTP " + response.status() + ")", response.status(), null);
    }
    return Optional.of(response.body());
  }

  private String readJobId(String body) {
    try {
      String jobId = objectMapper.readTree(body).path("jobId").asString("");
      return jobId.isBlank() ? null : jobId;
    } catch (JacksonException e) {
      return null;
    }
  }

  private static Raw raw(int status, byte[] body) {
    return new Raw(status, new String(body, StandardCharsets.UTF_8));
  }

  private static String brief(String body) {
    String oneLine = body == null ? "" : body.replaceAll("\\s+", " ").trim();
    return oneLine.length() > 300 ? oneLine.substring(0, 300) + "…" : oneLine;
  }

  private record Raw(int status, String body) {}
}
