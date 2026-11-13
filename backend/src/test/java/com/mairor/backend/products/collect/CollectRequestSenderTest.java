package com.mairor.backend.products.collect;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.products.repository.CatalogCollectRequestRepository;
import com.mairor.backend.users.support.AuthenticatedUser;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;
import software.amazon.awssdk.core.exception.SdkClientException;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/** 수집 요청을 큐에 보내기(S15P31A306-517): 커밋 직후 보내기, 실패 시 남겨 두기, 한도에 닿으면 끝내기. */
@Import({TestcontainersConfiguration.class, CollectRequestSenderTest.FakeQueueConfig.class})
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql,classpath:db/schema/executions.sql",
      "app.security.allowed-origins=http://localhost:3000",
      "catalog.collect.types=CLS_TINT",
      "catalog.collect.max-send-attempts=2"
    })
@AutoConfigureMockMvc
class CollectRequestSenderTest {

  private static final String CATEGORY = "CLS_LIP";
  private static final String TYPE = "CLS_TINT";

  /** 보낸 메시지를 남기고, {@code failures}가 남아 있으면 실패한다. */
  static class FakeQueue implements CollectJobQueue {
    final List<CollectJobMessage> sent = new ArrayList<>();
    int failures;

    @Override
    public boolean enabled() {
      return true;
    }

    @Override
    public void send(CollectJobMessage message) {
      if (failures > 0) {
        failures--;
        throw new CollectQueueException("가짜 실패", null);
      }
      sent.add(message);
    }
  }

  @TestConfiguration
  static class FakeQueueConfig {
    @Bean
    @Primary
    FakeQueue fakeQueue() {
      return new FakeQueue();
    }
  }

  @Autowired private MockMvc mockMvc;
  @Autowired private JdbcTemplate jdbc;
  @Autowired private FakeQueue queue;
  @Autowired private CollectRequestSender sender;
  @Autowired private CatalogCollectRequestRepository requests;
  @Autowired private ObjectMapper json;

  private UUID user;
  private String brand;

  @BeforeEach
  void setUp() {
    queue.sent.clear();
    queue.failures = 0;
    jdbc.update(
        "insert into product_categories values (?, '보내기 시험', true, true, 91) on conflict do nothing",
        CATEGORY);
    jdbc.update(
        "insert into product_types values (?, ?, '보내기 틴트', 1) on conflict do nothing",
        TYPE,
        CATEGORY);
    user = UUID.randomUUID();
    jdbc.update(
        "insert into users (id, email, provider, created_at, updated_at)"
            + " values (?, ?, 'LOCAL', now(), now())",
        user,
        user + "@example.com");
    brand = "보내기" + UUID.randomUUID().toString().substring(0, 8);
  }

  @AfterEach
  void cleanUp() {
    jdbc.update("delete from catalog_collect_requests where brand = ?", brand);
    jdbc.update("delete from pouch_items where user_id = ?", user);
    jdbc.update("delete from users where id = ?", user);
  }

  @Test
  void aNewRequestIsSentRightAfterTheRegistrationCommits() throws Exception {
    register("쥬시 틴트");

    Map<String, Object> row = onlyRequest();
    assertThat(row).containsEntry("status", "SENT").containsEntry("send_attempts", 1);
    assertThat(row.get("sent_at")).isNotNull();
    assertThat(queue.sent)
        .singleElement()
        .satisfies(
            message -> {
              assertThat(message.jobId()).isEqualTo(row.get("id").toString());
              assertThat(message.brand()).isEqualTo(brand);
              assertThat(message.name()).isEqualTo("쥬시 틴트");
              assertThat(message.url()).isNull();
              assertThat(message.typeHint()).isEqualTo(TYPE);
              assertThat(message.contractVersion()).isEqualTo(1);
            });
  }

  @Test
  void aFailedSendStaysQueuedAndTheSweeperSendsItLater() throws Exception {
    queue.failures = 1;
    register("쥬시 틴트");
    assertThat(onlyRequest()).containsEntry("status", "QUEUED").containsEntry("send_attempts", 1);

    Clock later = Clock.fixed(Instant.now().plusSeconds(60), java.time.ZoneOffset.UTC);
    new CollectRequestSendSweeper(requests, sender, later).sweep();

    assertThat(onlyRequest()).containsEntry("status", "SENT").containsEntry("send_attempts", 2);
    assertThat(queue.sent).hasSize(1);
  }

  @Test
  void aRequestThatKeepsFailingToSendEndsFailed() throws Exception {
    queue.failures = 5;
    register("쥬시 틴트");
    UUID id = (UUID) onlyRequest().get("id");

    assertThat(sender.send(id)).isEqualTo(CollectRequestSender.Sent.GAVE_UP);

    assertThat(onlyRequest())
        .containsEntry("status", "FAILED")
        .containsEntry("reason", CollectRequestSender.SEND_FAILED);
    assertThat(sender.send(id)).isEqualTo(CollectRequestSender.Sent.NOT_QUEUED);
  }

  @Test
  void theSqsMessageBodyFollowsTheCollectJobContract() {
    SqsClient client = mock(SqsClient.class);
    SqsCollectJobQueue sqs = new SqsCollectJobQueue(client, "https://sqs.example/q", json);
    CollectJobMessage message =
        new CollectJobMessage(
            1,
            "5f0c2a1e-8d3b-4c71-9a2e-1b7f3c9d4e10",
            "롬앤",
            null,
            "https://romand.co.kr/product/1",
            "LIP_TINT",
            Instant.parse("2026-11-12T00:00:00Z"));

    sqs.send(message);

    ArgumentCaptor<SendMessageRequest> sentRequest =
        ArgumentCaptor.forClass(SendMessageRequest.class);
    verify(client).sendMessage(sentRequest.capture());
    assertThat(sentRequest.getValue().queueUrl()).isEqualTo("https://sqs.example/q");
    JsonNode body = json.readTree(sentRequest.getValue().messageBody());
    assertThat(body.get("contractVersion").asInt()).isEqualTo(1);
    assertThat(body.get("jobId").asString()).isEqualTo(message.jobId());
    assertThat(body.get("name").isNull()).isTrue();
    assertThat(body.get("url").asString()).isEqualTo("https://romand.co.kr/product/1");
    assertThat(body.get("requestedAt").asString()).isEqualTo("2026-11-12T00:00:00Z");
  }

  @Test
  void anSqsErrorBecomesAQueueException() {
    SqsClient client = mock(SqsClient.class);
    when(client.sendMessage(any(SendMessageRequest.class)))
        .thenThrow(SdkClientException.create("연결 실패"));
    SqsCollectJobQueue sqs = new SqsCollectJobQueue(client, "https://sqs.example/q", json);

    org.assertj.core.api.Assertions.assertThatThrownBy(
            () -> sqs.send(new CollectJobMessage(1, "a", "b", "c", null, null, Instant.EPOCH)))
        .isInstanceOf(CollectJobQueue.CollectQueueException.class)
        .hasMessageContaining("sqs.example");
  }

  private void register(String name) throws Exception {
    String body =
        """
        {"registrationMode":"MANUAL","category":"%s","type":"%s","brand":"%s","name":"%s","shadeName":null}
        """
            .formatted(CATEGORY, TYPE, brand, name);
    mockMvc
        .perform(
            post("/v1/users/me/pouch-items")
                .with(
                    authentication(
                        UsernamePasswordAuthenticationToken.authenticated(
                            new AuthenticatedUser(user, "member@example.com"),
                            null,
                            List.of(new SimpleGrantedAuthority("ROLE_USER")))))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
        .andExpect(status().isCreated());
  }

  private Map<String, Object> onlyRequest() {
    List<Map<String, Object>> rows =
        jdbc.queryForList("select * from catalog_collect_requests where brand = ?", brand);
    assertThat(rows).hasSize(1);
    return rows.getFirst();
  }
}
