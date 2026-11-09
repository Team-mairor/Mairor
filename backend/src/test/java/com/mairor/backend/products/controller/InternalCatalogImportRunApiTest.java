package com.mairor.backend.products.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.common.security.InternalTokenFilter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.function.Consumer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/**
 * 카탈로그 적재 실행 API(열기·건 묶음·하트비트·끝내기)의 인증·요청 검증·응답 계약과 오류 코드. 처리 규칙은 {@code CatalogImportServiceTest}와
 * {@code CatalogImportRunServiceTest}가 본다. 건마다 자기 트랜잭션이라 이 테스트는 트랜잭션으로 감싸지 않고, 전후에 표를 비운다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql",
      "app.security.allowed-origins=http://localhost:3000",
      "app.internal.token=" + InternalCatalogImportRunApiTest.TOKEN,
      "catalog.color.min-quality.PRODUCT_PHOTO=0.8"
    })
@AutoConfigureMockMvc
class InternalCatalogImportRunApiTest {

  static final String TOKEN = "test-internal-token";
  private static final String BASE = "/v1/internal/catalog/import-runs";
  private static final Path SAMPLE =
      Path.of("..", "shared", "catalog-import", "samples", "etude_option_image.json");
  private static final ObjectMapper MAPPER = new ObjectMapper();

  @Autowired private MockMvc mockMvc;
  @Autowired private JdbcTemplate jdbc;

  @BeforeEach
  void setUp() {
    clean();
    jdbc.update(
        "insert into product_categories (code, label, matchable, shade_selectable, sort_order)"
            + " values ('EYE', '아이', true, true, 3)");
    jdbc.update(
        "insert into product_types (code, category_code, label, sort_order)"
            + " values ('MASCARA', 'EYE', '마스카라', 2)");
  }

  @AfterEach
  void tearDown() {
    clean();
  }

  private void clean() {
    for (String table :
        List.of(
            "product_shade_colors",
            "product_shade_option_aliases",
            "product_shades",
            "catalog_import_items",
            "products",
            "catalog_import_runs",
            "product_category_parts",
            "product_types",
            "product_categories")) {
      jdbc.update("delete from " + table);
    }
  }

  private static MockHttpServletRequestBuilder authorized(String path, String json) {
    return post(path)
        .header(InternalTokenFilter.HEADER, TOKEN)
        .contentType(MediaType.APPLICATION_JSON)
        .content(json);
  }

  private static String startBody(String runId) {
    return "{\"runId\":\""
        + runId
        + "\",\"seed\":\"OFFICIAL:etude.com\","
        + "\"collectorVersion\":\"0.1.0\",\"startedAt\":\"2026-11-08T21:30:00+09:00\","
        + "\"resultFile\":\"20261108-213000-etude.jsonl\"}";
  }

  private String open(String runId) throws Exception {
    MvcResult result =
        mockMvc
            .perform(authorized(BASE, startBody(runId)))
            .andExpect(status().isCreated())
            .andReturn();
    return MAPPER.readTree(result.getResponse().getContentAsString()).path("id").asString();
  }

  private static ObjectNode item(Consumer<ObjectNode> change) throws Exception {
    ObjectNode node = (ObjectNode) MAPPER.readTree(Files.readString(SAMPLE));
    change.accept(node);
    return node;
  }

  private static String items(ObjectNode... nodes) {
    ObjectNode root = MAPPER.createObjectNode();
    ArrayNode array = root.putArray("items");
    for (ObjectNode node : nodes) {
      array.add(node);
    }
    return MAPPER.writeValueAsString(root);
  }

  // --- 인증 ---

  @Test
  void everyRunEndpointRequiresTheInternalToken() throws Exception {
    String id = open("run-1");
    for (String path :
        List.of(
            BASE,
            BASE + "/" + id + "/items",
            BASE + "/" + id + "/heartbeat",
            BASE + "/" + id + "/finish")) {
      mockMvc
          .perform(post(path).contentType(MediaType.APPLICATION_JSON).content("{}"))
          .andExpect(status().isUnauthorized());
      mockMvc
          .perform(
              post(path)
                  .header(InternalTokenFilter.HEADER, "wrong")
                  .contentType(MediaType.APPLICATION_JSON)
                  .content("{}"))
          .andExpect(status().isUnauthorized());
    }
  }

  // --- 열기 ---

  @Test
  void openingARunReturns201AndOpeningItAgainResumesWith200() throws Exception {
    mockMvc
        .perform(authorized(BASE, startBody("run-1")))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.id").isNotEmpty())
        .andExpect(jsonPath("$.runId").value("run-1"))
        .andExpect(jsonPath("$.status").value("RUNNING"))
        .andExpect(jsonPath("$.resumed").value(false))
        .andExpect(jsonPath("$.finishedAt").doesNotExist());

    mockMvc
        .perform(authorized(BASE, startBody("run-1")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.resumed").value(true));
  }

  @Test
  void openingNeedsOnlyARunIdButRejectsBadValues() throws Exception {
    mockMvc.perform(authorized(BASE, "{\"runId\":\"run-min\"}")).andExpect(status().isCreated());
    mockMvc
        .perform(authorized(BASE, "{\"runId\":\"  \"}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
    mockMvc.perform(authorized(BASE, "{}")).andExpect(status().isBadRequest());
    mockMvc
        .perform(authorized(BASE, "{\"runId\":\"" + "x".repeat(101) + "\"}"))
        .andExpect(status().isBadRequest());
    mockMvc
        .perform(authorized(BASE, "{\"runId\":\"r\",\"resultFile\":\"../etc/passwd\"}"))
        .andExpect(status().isBadRequest());
    mockMvc
        .perform(authorized(BASE, "{\"runId\":\"r\",\"resultFile\":\"a/b.jsonl\"}"))
        .andExpect(status().isBadRequest());
  }

  @Test
  void openingAFinishedRunIdIsAConflict() throws Exception {
    String id = open("run-1");
    mockMvc
        .perform(authorized(BASE + "/" + id + "/finish", "{\"status\":\"COMPLETED\"}"))
        .andExpect(status().isOk());

    mockMvc
        .perform(authorized(BASE, startBody("run-1")))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("IMPORT_RUN_CLOSED"));
  }

  // --- 건 묶음 ---

  @Test
  void aBatchReturnsOneResultPerItemInOrderWithTheOutcomes() throws Exception {
    String id = open("run-1");
    ObjectNode bad = item(n -> n.put("itemKey", "000002"));
    bad.remove("sourceProductId");

    MvcResult result =
        mockMvc
            .perform(authorized(BASE + "/" + id + "/items", items(item(n -> {}), bad)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.results.length()").value(2))
            .andExpect(jsonPath("$.results[0].index").value(0))
            .andExpect(jsonPath("$.results[0].itemKey").value("000003"))
            .andExpect(jsonPath("$.results[0].outcome").value("NEW"))
            .andExpect(jsonPath("$.results[0].colorsApplied").value(2))
            .andExpect(jsonPath("$.results[0].duplicate").value(false))
            .andExpect(jsonPath("$.results[0].recorded").value(true))
            .andExpect(jsonPath("$.results[0].productId").isNotEmpty())
            .andExpect(jsonPath("$.results[1].outcome").value("INVALID"))
            .andExpect(jsonPath("$.results[1].itemKey").value("000002"))
            .andExpect(jsonPath("$.results[1].reasons[0]").value("REQUIRED"))
            .andReturn();

    JsonNode second =
        MAPPER.readTree(result.getResponse().getContentAsString()).path("results").get(1);
    assertThat(second.path("message").asString()).contains("sourceProductId");
  }

  @Test
  void sendingTheSameBatchAgainReturnsStoredResultsAsDuplicates() throws Exception {
    String id = open("run-1");
    String body = items(item(n -> {}));
    mockMvc.perform(authorized(BASE + "/" + id + "/items", body)).andExpect(status().isOk());

    mockMvc
        .perform(authorized(BASE + "/" + id + "/items", body))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.results[0].outcome").value("NEW"))
        .andExpect(jsonPath("$.results[0].duplicate").value(true));
    assertThat(jdbc.queryForObject("select count(*) from products", Integer.class)).isEqualTo(1);
  }

  @Test
  void aBatchWithTheWrongShapeIsRejectedAsAWhole() throws Exception {
    String id = open("run-1");

    mockMvc
        .perform(authorized(BASE + "/" + id + "/items", "{\"items\":{}}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
    mockMvc
        .perform(authorized(BASE + "/" + id + "/items", "{\"items\":[]}"))
        .andExpect(status().isBadRequest());
    mockMvc
        .perform(authorized(BASE + "/" + id + "/items", "{}"))
        .andExpect(status().isBadRequest());
    ObjectNode root = MAPPER.createObjectNode();
    ArrayNode many = root.putArray("items");
    for (int i = 0; i < 101; i++) {
      many.add(MAPPER.createObjectNode());
    }
    mockMvc
        .perform(authorized(BASE + "/" + id + "/items", MAPPER.writeValueAsString(root)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("items"));
  }

  @Test
  void itemsForAnUnknownOrFinishedRunAreRefused() throws Exception {
    mockMvc
        .perform(
            authorized(BASE + "/00000000-0000-4000-8000-000000000001/items", items(item(n -> {}))))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("IMPORT_RUN_NOT_FOUND"));

    String id = open("run-1");
    mockMvc
        .perform(authorized(BASE + "/" + id + "/finish", "{\"status\":\"FAILED\"}"))
        .andExpect(status().isOk());
    mockMvc
        .perform(authorized(BASE + "/" + id + "/items", items(item(n -> {}))))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("IMPORT_RUN_CLOSED"));
    assertThat(jdbc.queryForObject("select count(*) from catalog_import_items", Integer.class))
        .isZero();
  }

  // --- 하트비트 ---

  @Test
  void aHeartbeatReturnsTheRunAndFailsForMissingOrFinishedRuns() throws Exception {
    String id = open("run-1");

    mockMvc
        .perform(authorized(BASE + "/" + id + "/heartbeat", ""))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("RUNNING"))
        .andExpect(jsonPath("$.lastHeartbeatAt").isNotEmpty());
    mockMvc
        .perform(authorized(BASE + "/00000000-0000-4000-8000-000000000001/heartbeat", ""))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("IMPORT_RUN_NOT_FOUND"));
    mockMvc
        .perform(authorized(BASE + "/" + id + "/finish", "{\"status\":\"COMPLETED\"}"))
        .andExpect(status().isOk());
    mockMvc
        .perform(authorized(BASE + "/" + id + "/heartbeat", ""))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("IMPORT_RUN_CLOSED"));
  }

  // --- 끝내기 ---

  @Test
  void finishingSetsTheStatusAndTheFinishTimeAndRepeatingItIsFine() throws Exception {
    String id = open("run-1");

    mockMvc
        .perform(authorized(BASE + "/" + id + "/finish", "{\"status\":\"COMPLETED\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("COMPLETED"))
        .andExpect(jsonPath("$.finishedAt").isNotEmpty());
    mockMvc
        .perform(authorized(BASE + "/" + id + "/finish", "{\"status\":\"COMPLETED\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("COMPLETED"));
    mockMvc
        .perform(authorized(BASE + "/" + id + "/finish", "{\"status\":\"FAILED\"}"))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("IMPORT_RUN_CLOSED"));
  }

  @Test
  void finishingRequiresACollectorStatus() throws Exception {
    String id = open("run-1");

    for (String body :
        List.of(
            "{}",
            "{\"status\":\"ABANDONED\"}",
            "{\"status\":\"RUNNING\"}",
            "{\"status\":\"DONE\"}")) {
      mockMvc
          .perform(authorized(BASE + "/" + id + "/finish", body))
          .andExpect(status().isBadRequest());
    }
    mockMvc
        .perform(
            authorized(
                BASE + "/00000000-0000-4000-8000-000000000001/finish",
                "{\"status\":\"COMPLETED\"}"))
        .andExpect(status().isNotFound());
  }

  // --- 통계 ---

  @Test
  void runStatsReportTheOutcomesAndKeepFailuresVisible() throws Exception {
    String id = open("run-1");
    ObjectNode bad = item(n -> n.put("itemKey", "000002"));
    bad.remove("sourceProductId");
    mockMvc
        .perform(authorized(BASE + "/" + id + "/items", items(item(n -> {}), bad)))
        .andExpect(status().isOk());
    mockMvc
        .perform(authorized(BASE + "/" + id + "/finish", "{\"status\":\"COMPLETED\"}"))
        .andExpect(status().isOk());

    mockMvc
        .perform(get(BASE + "/" + id + "/stats").header(InternalTokenFilter.HEADER, TOKEN))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.run.status").value("COMPLETED"))
        .andExpect(jsonPath("$.total").value(2))
        .andExpect(jsonPath("$.created").value(1))
        .andExpect(jsonPath("$.failed").value(1))
        .andExpect(jsonPath("$.colorsApplied").value(2))
        .andExpect(jsonPath("$.byOutcome.NEW").value(1))
        .andExpect(jsonPath("$.byOutcome.INVALID").value(1))
        .andExpect(jsonPath("$.byOutcome.FAILED").value(0))
        .andExpect(jsonPath("$.reasons.REQUIRED").value(1))
        .andExpect(jsonPath("$.problemCount").value(1))
        .andExpect(jsonPath("$.problems[0].itemKey").value("000002"))
        .andExpect(jsonPath("$.problems[0].outcome").value("INVALID"));
  }

  @Test
  void runStatsNeedTheTokenAndAnExistingRun() throws Exception {
    String id = open("run-1");

    mockMvc.perform(get(BASE + "/" + id + "/stats")).andExpect(status().isUnauthorized());
    mockMvc
        .perform(
            get(BASE + "/00000000-0000-4000-8000-000000000001/stats")
                .header(InternalTokenFilter.HEADER, TOKEN))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("IMPORT_RUN_NOT_FOUND"));
  }

  @Test
  void qualityShowsTheCurrentColorStateAndCanBeLimitedToASource() throws Exception {
    String id = open("run-1");
    mockMvc
        .perform(authorized(BASE + "/" + id + "/items", items(item(n -> {}))))
        .andExpect(status().isOk());
    String quality = "/v1/internal/catalog/quality";

    mockMvc
        .perform(get(quality).header(InternalTokenFilter.HEADER, TOKEN))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.source").doesNotExist())
        .andExpect(jsonPath("$.products").value(1))
        .andExpect(jsonPath("$.slots.total").value(2))
        .andExpect(jsonPath("$.slots.usable").value(2))
        .andExpect(jsonPath("$.slots.usableRatio").value(1.0))
        .andExpect(jsonPath("$.shades.usable").value(2))
        .andExpect(jsonPath("$.usableBySource.PRODUCT_PHOTO").value(2));
    mockMvc
        .perform(
            get(quality)
                .param("source", "OFFICIAL:nowhere.example")
                .header(InternalTokenFilter.HEADER, TOKEN))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.source").value("OFFICIAL:nowhere.example"))
        .andExpect(jsonPath("$.products").value(0))
        .andExpect(jsonPath("$.slots.usableRatio").doesNotExist());
    mockMvc.perform(get(quality)).andExpect(status().isUnauthorized());
  }
}
