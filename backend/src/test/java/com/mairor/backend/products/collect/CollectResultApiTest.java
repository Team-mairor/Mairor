package com.mairor.backend.products.collect;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.common.security.InternalTokenFilter;
import com.mairor.backend.products.entity.CatalogCollectRequest;
import com.mairor.backend.products.entity.CollectTrigger;
import com.mairor.backend.products.repository.CatalogCollectRequestRepository;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Map;
import java.util.UUID;
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
import org.springframework.test.web.servlet.ResultActions;

/** 수집 워커 결과 콜백(S15P31A306-517)과 결과가 오지 않은 요청 정리를 PostgreSQL 로 확인한다. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql,classpath:db/schema/executions.sql",
      "app.security.allowed-origins=http://localhost:3000",
      "app.internal.token=" + CollectResultApiTest.TOKEN
    })
@AutoConfigureMockMvc
class CollectResultApiTest {

  static final String TOKEN = "collect-result-token";
  private static final String CATEGORY = "CLR_LIP";
  private static final String TYPE = "CLR_TINT";

  @Autowired private MockMvc mockMvc;
  @Autowired private JdbcTemplate jdbc;
  @Autowired private CatalogCollectRequestRepository requests;
  @Autowired private CollectResultService results;
  @Autowired private CatalogCollectProperties properties;

  private String brand;

  @BeforeEach
  void setUp() {
    jdbc.update(
        "insert into product_categories values (?, '결과 시험', true, true, 92) on conflict do nothing",
        CATEGORY);
    jdbc.update(
        "insert into product_types values (?, ?, '결과 틴트', 1) on conflict do nothing",
        TYPE,
        CATEGORY);
    brand = "결과" + UUID.randomUUID().toString().substring(0, 8);
  }

  @AfterEach
  void cleanUp() {
    jdbc.update("delete from catalog_collect_requests where brand = ?", brand);
    jdbc.update(
        "delete from product_shades where product_id in (select id from products where brand = ?)",
        brand);
    jdbc.update("delete from products where brand = ?", brand);
  }

  @Test
  void aCollectedResultResolvesWhenTheProductAndShadeAreNowInTheCatalog() throws Exception {
    UUID id = sentRequest("쥬시 래스팅 틴트", null, "01 니어");
    UUID product = product("쥬시 래스팅 틴트", "12", "https://shop.example/p/12");
    shade(product, "01 니어");

    send(id, collected(id, "12", "https://shop.example/p/12"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("RESOLVED"))
        .andExpect(jsonPath("$.changed").value(true));

    Map<String, Object> row = row(id);
    assertThat(row).containsEntry("status", "RESOLVED").containsEntry("result_status", "COLLECTED");
    assertThat(row.get("result_file")).isEqualTo("20261112-000012-job-a.jsonl");
    assertThat(row.get("import_run_id")).isNull();
  }

  @Test
  void aCollectedResultWithoutTheRequestedShadeStaysUnresolved() throws Exception {
    UUID id = sentRequest("쥬시 래스팅 틴트", null, "05 레드");
    shade(product("쥬시 래스팅 틴트", "12", "https://shop.example/p/12"), "01 니어");

    send(id, collected(id, "12", "https://shop.example/p/12"))
        .andExpect(jsonPath("$.status").value("UNRESOLVED"))
        .andExpect(jsonPath("$.reason").value("SHADE_NOT_FOUND"));
  }

  @Test
  void aCollectedResultWhoseProductWasHeldBackIsUnresolved() throws Exception {
    UUID id = sentRequest("쥬시 래스팅 틴트", null, null);

    send(id, collected(id, "12", "https://shop.example/p/12"))
        .andExpect(jsonPath("$.status").value("UNRESOLVED"))
        .andExpect(jsonPath("$.reason").value("NOT_IN_CATALOG"));
  }

  @Test
  void aUrlRequestFindsItsProductByTheCollectedSourceNumber() throws Exception {
    UUID id = sentRequest(null, "https://shop.example/p/12", "01 니어");
    shade(product("공식 이름이 다른 틴트", "12", "https://shop.example/p/12"), "01 니어");

    send(id, collected(id, "12", "https://shop.example/p/12"))
        .andExpect(jsonPath("$.status").value("RESOLVED"));
  }

  @Test
  void otherWorkerStatusesMapToNotFoundAndFailed() throws Exception {
    UUID empty = sentRequest("없는 틴트", null, null);
    UUID unsupported = sentRequest("다른 틴트", null, null);
    UUID blocked = sentRequest("막힌 틴트", null, null);

    send(empty, ended(empty, "SEARCH_EMPTY", "NOT_FOUND"))
        .andExpect(jsonPath("$.status").value("NOT_FOUND"))
        .andExpect(jsonPath("$.reason").value("SEARCH_EMPTY"));
    send(unsupported, ended(unsupported, "UNSUPPORTED_SOURCE", "SITE_DISABLED"))
        .andExpect(jsonPath("$.status").value("NOT_FOUND"))
        .andExpect(jsonPath("$.reason").value("UNSUPPORTED_SOURCE:SITE_DISABLED"));
    send(blocked, ended(blocked, "BLOCKED", "BLOCKED:shop.example"))
        .andExpect(jsonPath("$.status").value("FAILED"))
        .andExpect(jsonPath("$.reason").value("BLOCKED:shop.example"));
  }

  @Test
  void theSameResultAgainChangesNothing() throws Exception {
    UUID id = sentRequest("없는 틴트", null, null);
    send(id, ended(id, "SEARCH_EMPTY", "NOT_FOUND")).andExpect(status().isOk());

    send(id, ended(id, "FAILED", "RETRIES_EXHAUSTED"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("NOT_FOUND"))
        .andExpect(jsonPath("$.changed").value(false));
  }

  @Test
  void aMismatchedJobIdAnUnknownJobAndAMissingTokenAreRejected() throws Exception {
    UUID id = sentRequest("없는 틴트", null, null);
    UUID unknown = UUID.randomUUID();

    send(id, ended(unknown, "SEARCH_EMPTY", "NOT_FOUND")).andExpect(status().isBadRequest());
    send(unknown, ended(unknown, "SEARCH_EMPTY", "NOT_FOUND")).andExpect(status().isNotFound());
    mockMvc
        .perform(
            post(path(id))
                .contentType(MediaType.APPLICATION_JSON)
                .content(ended(id, "SEARCH_EMPTY", "NOT_FOUND")))
        .andExpect(status().isUnauthorized());
    assertThat(row(id)).containsEntry("status", "SENT");
  }

  @Test
  void aSentRequestWithoutAResultForTooLongIsTimedOut() {
    UUID stale = sentRequest("오래된 틴트", null, null);
    Clock later =
        Clock.fixed(Instant.now().plus(properties.resultTimeout()).plusSeconds(60), ZoneOffset.UTC);

    new CollectResultWatcher(requests, results, properties, later).check();

    assertThat(row(stale))
        .containsEntry("status", "FAILED")
        .containsEntry("reason", CollectResultService.RESULT_TIMEOUT);
  }

  @Test
  void theRequestListShowsStatusesAndFiltersByStatus() throws Exception {
    UUID done = sentRequest("없는 틴트", null, null);
    UUID open = sentRequest("보낸 틴트", null, null);
    send(done, ended(done, "SEARCH_EMPTY", "NOT_FOUND")).andExpect(status().isOk());

    mockMvc
        .perform(
            get("/v1/internal/catalog/collect-requests")
                .param("status", "NOT_FOUND")
                .param("limit", "200")
                .header(InternalTokenFilter.HEADER, TOKEN))
        .andExpect(status().isOk())
        .andExpect(
            jsonPath("$[?(@.requestId == '%s')].reason".formatted(done)).value("SEARCH_EMPTY"))
        .andExpect(jsonPath("$[?(@.requestId == '%s')]".formatted(open)).isEmpty());
    mockMvc
        .perform(
            get("/v1/internal/catalog/collect-requests")
                .param("limit", "0")
                .header(InternalTokenFilter.HEADER, TOKEN))
        .andExpect(status().isBadRequest());
    mockMvc
        .perform(
            get("/v1/internal/catalog/collect-requests")
                .param("status", "PAUSED")
                .header(InternalTokenFilter.HEADER, TOKEN))
        .andExpect(status().isBadRequest());
  }

  private UUID sentRequest(String name, String url, String shadeName) {
    String key = url != null ? "URL|" + url + "|" + brand : "NAME|" + brand + "|" + name;
    CatalogCollectRequest request =
        new CatalogCollectRequest(
            CollectTrigger.USER, key, CATEGORY, TYPE, brand, name, url, shadeName);
    request.markSent(Instant.now());
    requests.saveAndFlush(request);
    return request.getId();
  }

  private UUID product(String name, String sourceId, String sourceUrl) {
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into products (id, brand, name, brand_normalized, name_normalized, category_code,"
            + " type_code, source, source_product_id, source_url, created_at, updated_at)"
            + " values (?, ?, ?, lower(?), lower(?), ?, ?, 'OFFICIAL:shop.example', ?, ?, now(),"
            + " now())",
        id,
        brand,
        name,
        brand,
        name,
        CATEGORY,
        TYPE,
        brand + "-" + sourceId,
        sourceUrl);
    return id;
  }

  private void shade(UUID product, String name) {
    jdbc.update(
        "insert into product_shades (id, product_id, name, name_normalized, sort_order,"
            + " created_at, updated_at) values (gen_random_uuid(), ?, ?, lower(?), 1, now(), now())",
        product,
        name,
        name);
  }

  private String collected(UUID id, String sourceId, String sourceUrl) {
    return """
        {"contractVersion":1,"jobId":"%s","status":"COLLECTED","reason":null,
         "resultFile":"20261112-000012-job-a.jsonl","runId":"r-1","importRunId":"%s",
         "products":[{"itemKey":"000001","source":"OFFICIAL:shop.example",
           "sourceProductId":"%s","sourceUrl":"%s"}],
         "failedProducts":[],"finishedAt":"2026-11-12T09:03:10+09:00"}
        """
        .formatted(id, UUID.randomUUID(), brand + "-" + sourceId, sourceUrl);
  }

  private static String ended(UUID id, String status, String reason) {
    return """
        {"contractVersion":1,"jobId":"%s","status":"%s","reason":"%s","resultFile":null,
         "runId":null,"importRunId":null,"products":[],"failedProducts":[],
         "finishedAt":"2026-11-12T09:03:10+09:00"}
        """
        .formatted(id, status, reason);
  }

  private ResultActions send(UUID id, String body) throws Exception {
    return mockMvc.perform(
        post(path(id))
            .header(InternalTokenFilter.HEADER, TOKEN)
            .contentType(MediaType.APPLICATION_JSON)
            .content(body));
  }

  private static String path(UUID id) {
    return "/v1/internal/catalog/collect-jobs/" + id + "/result";
  }

  private Map<String, Object> row(UUID id) {
    return jdbc.queryForMap("select * from catalog_collect_requests where id = ?", id);
  }
}
