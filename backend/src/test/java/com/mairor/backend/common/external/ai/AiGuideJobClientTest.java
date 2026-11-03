package com.mairor.backend.common.external.ai;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withException;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import java.net.ConnectException;
import java.time.Duration;
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
    AiProperties properties =
        new AiProperties(
            "http://ai:8000",
            "http://api:8080/api",
            Duration.ofSeconds(1),
            Duration.ofSeconds(1),
            Duration.ofHours(24),
            Duration.ofMinutes(60),
            Duration.ofSeconds(60));
    RestClient.Builder builder = RestClient.builder();
    server = MockRestServiceServer.bindTo(builder).build();
    client = new AiGuideJobClient(properties, builder.build(), JsonMapper.builder().build());
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
