package com.mairor.backend.common.external.llm;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.jsonPath;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withException;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import java.io.IOException;
import java.net.SocketTimeoutException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.ExpectedCount;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import tools.jackson.databind.json.JsonMapper;

/** Gemini 호출: 요청 본문, 답 해석, 재시도와 실패 분류. 실제 대기 없이 재시도 간격만 기록한다. */
class GeminiClientTest {

  private static final String URL =
      "https://gms.ssafy.io/gmsapi/generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent";
  private static final LlmRequest REQUEST =
      new LlmRequest(
          "https://www.youtube.com/watch?v=VxAXD6PP76I", "단계를 나눠라", "{\"type\": \"OBJECT\"}", 0.2);
  private static final String OK =
      """
      {"candidates": [{"content": {"parts": [{"text": "{\\"steps\\": "}, {"text": "[]}"}]},
                       "finishReason": "STOP"}],
       "usageMetadata": {"promptTokenCount": 155925, "candidatesTokenCount": 6372,
                         "thoughtsTokenCount": 5743}}
      """;

  private MockRestServiceServer server;
  private final List<Duration> waits = new ArrayList<>();
  private GeminiClient client;

  @BeforeEach
  void setUp() {
    client = client("test-key");
  }

  private GeminiClient client(String key) {
    GeminiProperties properties =
        new GeminiProperties(
            "https://gms.ssafy.io/gmsapi/generativelanguage.googleapis.com",
            key,
            "x-goog-api-key",
            "gemini-2.5-flash",
            Duration.ofSeconds(1),
            Duration.ofSeconds(1),
            3,
            Duration.ofSeconds(5));
    RestClient.Builder builder = RestClient.builder();
    server = MockRestServiceServer.bindTo(builder).build();
    return new GeminiClient(properties, builder.build(), JsonMapper.builder().build(), waits::add);
  }

  @Test
  void sendsTheVideoPromptAndSchemaAndReadsTheAnswer() {
    server
        .expect(requestTo(URL))
        .andExpect(method(HttpMethod.POST))
        .andExpect(header("x-goog-api-key", "test-key"))
        .andExpect(
            jsonPath("$.contents[0].parts[0].fileData.fileUri")
                .value("https://www.youtube.com/watch?v=VxAXD6PP76I"))
        .andExpect(jsonPath("$.contents[0].parts[1].text").value("단계를 나눠라"))
        .andExpect(jsonPath("$.generationConfig.responseMimeType").value("application/json"))
        .andExpect(jsonPath("$.generationConfig.responseSchema.type").value("OBJECT"))
        .andExpect(jsonPath("$.generationConfig.temperature").value(0.2))
        .andRespond(withSuccess(OK, MediaType.APPLICATION_JSON));

    LlmResult result = client.generate(REQUEST);

    assertThat(result.text()).isEqualTo("{\"steps\": []}");
    assertThat(result.provider()).isEqualTo("GMS");
    assertThat(result.model()).isEqualTo("gemini-2.5-flash");
    assertThat(result.inputTokens()).isEqualTo(155925);
    assertThat(result.outputTokens()).as("생각 토큰 포함").isEqualTo(6372 + 5743);
    assertThat(result.attempts()).isEqualTo(1);
    server.verify();
  }

  @Test
  void tooManyRequestsThenSuccessRetries() {
    server.expect(requestTo(URL)).andRespond(withStatus(HttpStatus.TOO_MANY_REQUESTS));
    server.expect(requestTo(URL)).andRespond(withSuccess(OK, MediaType.APPLICATION_JSON));

    LlmResult result = client.generate(REQUEST);

    assertThat(result.attempts()).isEqualTo(2);
    assertThat(waits).containsExactly(Duration.ofSeconds(5));
    server.verify();
  }

  @Test
  void serverErrorsAndTimeoutsUseUpTheAttemptsWithDoublingWaits() {
    server.expect(requestTo(URL)).andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE));
    server.expect(requestTo(URL)).andRespond(withException(new SocketTimeoutException("read")));
    server.expect(requestTo(URL)).andRespond(withStatus(HttpStatus.BAD_GATEWAY));

    assertThatThrownBy(() -> client.generate(REQUEST))
        .isInstanceOfSatisfying(
            LlmException.class,
            e -> {
              assertThat(e.kind()).isEqualTo(LlmException.Kind.UNAVAILABLE);
              assertThat(e.status()).isEqualTo(502);
            });
    assertThat(waits).containsExactly(Duration.ofSeconds(5), Duration.ofSeconds(10));
    server.verify();
  }

  @Test
  void clientErrorIsRejectedWithoutRetry() {
    server
        .expect(ExpectedCount.once(), requestTo(URL))
        .andRespond(
            withStatus(HttpStatus.BAD_REQUEST)
                .body("{\"error\": {\"message\": \"Video is private\"}}")
                .contentType(MediaType.APPLICATION_JSON));

    assertThatThrownBy(() -> client.generate(REQUEST))
        .isInstanceOfSatisfying(
            LlmException.class,
            e -> {
              assertThat(e.kind()).isEqualTo(LlmException.Kind.REJECTED);
              assertThat(e.status()).isEqualTo(400);
              assertThat(e.getMessage()).contains("Video is private");
            });
    assertThat(waits).isEmpty();
    server.verify();
  }

  @Test
  void truncatedOrBlockedAnswersAreInvalid() {
    server
        .expect(requestTo(URL))
        .andRespond(
            withSuccess(
                """
                {"candidates": [{"content": {"parts": [{"text": "{\\"steps\\": ["}]},
                                 "finishReason": "MAX_TOKENS"}]}
                """,
                MediaType.APPLICATION_JSON));
    assertThatThrownBy(() -> client.generate(REQUEST))
        .isInstanceOfSatisfying(
            LlmException.class,
            e -> {
              assertThat(e.kind()).isEqualTo(LlmException.Kind.INVALID_RESPONSE);
              assertThat(e.getMessage()).contains("MAX_TOKENS");
            });

    server.reset();
    server
        .expect(requestTo(URL))
        .andRespond(
            withSuccess(
                "{\"promptFeedback\": {\"blockReason\": \"SAFETY\"}}", MediaType.APPLICATION_JSON));
    assertThatThrownBy(() -> client.generate(REQUEST))
        .isInstanceOfSatisfying(
            LlmException.class,
            e -> {
              assertThat(e.kind()).isEqualTo(LlmException.Kind.INVALID_RESPONSE);
              assertThat(e.getMessage()).contains("SAFETY");
            });
  }

  @Test
  void withoutAKeyNothingIsSent() throws IOException {
    GeminiClient noKey = client(" ");

    assertThatThrownBy(() -> noKey.generate(REQUEST))
        .isInstanceOfSatisfying(
            LlmException.class,
            e -> assertThat(e.kind()).isEqualTo(LlmException.Kind.NOT_CONFIGURED));
    server.verify();
  }
}
