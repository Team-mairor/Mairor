package com.mairor.backend.common.external.ai;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withException;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.ConnectException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import tools.jackson.databind.json.JsonMapper;

class AiGuideJobClientTest {

  private static final String JOBS = "http://ai:8000/api/v1/guide-jobs";

  private MockRestServiceServer server;
  private AiGuideJobClient client;

  @BeforeEach
  void setUp() {
    RestClient.Builder builder = RestClient.builder();
    server = MockRestServiceServer.bindTo(builder).build();
    client =
        new AiGuideJobClient(
            properties("http://ai:8000"), builder.build(), JsonMapper.builder().build());
  }

  private static AiProperties properties(String baseUrl) {
    return new AiProperties(
        baseUrl,
        "http://api:8080/api",
        Duration.ofSeconds(1),
        Duration.ofSeconds(1),
        Duration.ofHours(24),
        Duration.ofMinutes(60),
        Duration.ofSeconds(60));
  }

  /**
   * 실제 HTTP 로 보낸다(위 테스트들은 HTTP 를 거치지 않는다). AI 서버(uvicorn)는 {@code Upgrade: h2c} 가 붙은 요청의 본문을 읽지 않아
   * 400(본문 없음)으로 거절했다(11.04 운영 E2E). 운영과 같은 생성자로 만든 클라이언트가 업그레이드 없이 본문을 보내는지 본다.
   */
  @Test
  void sendsTheBodyOverPlainHttp11WithoutAnH2cUpgrade() throws IOException {
    AtomicReference<String> upgrade = new AtomicReference<>("not received");
    AtomicReference<String> body = new AtomicReference<>();
    HttpServer http =
        HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
    http.createContext(
        "/api/v1/guide-jobs",
        exchange -> {
          upgrade.set(exchange.getRequestHeaders().getFirst("Upgrade"));
          body.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
          byte[] response =
              "{\"jobId\": \"real-1\", \"status\": \"QUEUED\"}".getBytes(StandardCharsets.UTF_8);
          exchange.getResponseHeaders().set("Content-Type", "application/json");
          exchange.sendResponseHeaders(202, response.length);
          exchange.getResponseBody().write(response);
          exchange.close();
        });
    http.start();
    try {
      String baseUrl = "http://127.0.0.1:" + http.getAddress().getPort();
      AiGuideJobClient real =
          new AiGuideJobClient(
              properties(baseUrl), RestClient.builder(), JsonMapper.builder().build());
      String requestJson = "{\"callbackUrl\": \"http://api:8080/api/cb\"}";

      assertThat(real.submit(requestJson)).isEqualTo("real-1");
      assertThat(upgrade.get()).as("Upgrade 헤더").isNull();
      assertThat(body.get()).isEqualTo(requestJson);
    } finally {
      http.stop(0);
    }
  }

  @Test
  void submitSendsTheBodyAndReturnsTheJobId() {
    server
        .expect(requestTo(JOBS))
        .andExpect(method(HttpMethod.POST))
        .andExpect(content().json("{\"callbackUrl\": \"http://api:8080/api/cb\"}"))
        .andRespond(
            withStatus(HttpStatus.ACCEPTED)
                .contentType(MediaType.APPLICATION_JSON)
                .body("{\"jobId\": \"8728c83b0d124c74a23863a50d4d7c0c\", \"status\": \"QUEUED\"}"));

    assertThat(client.submit("{\"callbackUrl\": \"http://api:8080/api/cb\"}"))
        .isEqualTo("8728c83b0d124c74a23863a50d4d7c0c");
    server.verify();
  }

  @Test
  void serverErrorOrNoConnectionIsTriedOnceMore() {
    server.expect(requestTo(JOBS)).andRespond(withException(new ConnectException("refused")));
    server
        .expect(requestTo(JOBS))
        .andRespond(
            withStatus(HttpStatus.ACCEPTED)
                .contentType(MediaType.APPLICATION_JSON)
                .body("{\"jobId\": \"j2\", \"status\": \"QUEUED\"}"));

    assertThat(client.submit("{}")).isEqualTo("j2");
    server.verify();
  }

  @Test
  void validationErrorIsNotRetried() {
    server
        .expect(requestTo(JOBS))
        .andRespond(
            withStatus(HttpStatus.BAD_REQUEST)
                .contentType(MediaType.APPLICATION_JSON)
                .body("{\"code\": \"VALIDATION_FAILED\", \"message\": \"frames.items.3.stepId\"}"));

    assertThatThrownBy(() -> client.submit("{}"))
        .isInstanceOfSatisfying(
            AiServerException.class,
            e -> {
              assertThat(e.status()).isEqualTo(400);
              assertThat(e.getMessage()).contains("VALIDATION_FAILED");
            });
    server.verify();
  }

  @Test
  void twoServerErrorsFail() {
    server.expect(requestTo(JOBS)).andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE));
    server.expect(requestTo(JOBS)).andRespond(withStatus(HttpStatus.BAD_GATEWAY));

    assertThatThrownBy(() -> client.submit("{}"))
        .isInstanceOfSatisfying(
            AiServerException.class, e -> assertThat(e.status()).isEqualTo(502));
  }

  @Test
  void findReturnsTheStatusBodyOrEmptyWhenTheJobIsGone() {
    server
        .expect(requestTo(JOBS + "/j1"))
        .andRespond(
            withSuccess(
                "{\"jobId\": \"j1\", \"status\": \"RUNNING\"}", MediaType.APPLICATION_JSON));
    server.expect(requestTo(JOBS + "/gone")).andRespond(withStatus(HttpStatus.NOT_FOUND));

    assertThat(client.find("j1")).hasValueSatisfying(b -> assertThat(b).contains("RUNNING"));
    assertThat(client.find("gone")).isEmpty();
  }
}
