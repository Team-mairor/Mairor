package com.mairor.backend.products.imports;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.doAnswer;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.products.entity.CatalogImportRun;
import com.mairor.backend.products.entity.ImportItemOutcome;
import com.mairor.backend.products.entity.ImportRunStatus;
import com.mairor.backend.products.imports.CatalogImportFileService.FileImportResult;
import com.mairor.backend.products.imports.CatalogImportService.ItemResult;
import com.mairor.backend.products.repository.CatalogImportRunRepository;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

/**
 * 오류 복구와 동시 처리에서 생기던 세 가지 문제의 재현 테스트: 이미 확정된 건을 실패 기록이 덮어쓰는 일, itemKey 없는 틀린 줄 때문에 파일 이어받기가 멈추는 일,
 * 실행이 끝난 뒤에 진행 중이던 건이 커밋되는 일.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql,classpath:db/schema/executions.sql",
      "app.security.allowed-origins=http://localhost:3000",
      "catalog.color.min-quality.PRODUCT_PHOTO=0.8"
    })
class CatalogImportRaceTest {

  private static final Path SAMPLE =
      Path.of("..", "shared", "catalog-import", "samples", "etude_option_image.json");
  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final Instant NOW = Instant.parse("2026-11-08T12:00:00Z");
  private static final Path DIRECTORY = newDirectory();

  private static Path newDirectory() {
    try {
      return Files.createTempDirectory("catalog-runs-race-test");
    } catch (java.io.IOException e) {
      throw new IllegalStateException(e);
    }
  }

  @DynamicPropertySource
  static void directory(DynamicPropertyRegistry registry) {
    registry.add("catalog.import.result-dir", DIRECTORY::toString);
  }

  @Autowired private CatalogImportService service;
  @Autowired private CatalogImportRunService runService;
  @Autowired private CatalogImportFileService fileService;
  @Autowired private CatalogImportRunRepository runs;
  @Autowired private JdbcTemplate jdbc;
  @MockitoSpyBean private CatalogMatchPlanner planner;

  @BeforeEach
  void setUp() throws Exception {
    clean();
    jdbc.update(
        "insert into product_categories (code, label, matchable, shade_selectable, sort_order)"
            + " values ('EYE', '아이', true, true, 3)");
    jdbc.update(
        "insert into product_types (code, category_code, label, sort_order)"
            + " values ('MASCARA', 'EYE', '마스카라', 2)");
  }

  @AfterEach
  void tearDown() throws Exception {
    clean();
  }

  private void clean() throws Exception {
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
    try (var stream = Files.list(DIRECTORY)) {
      for (Path file : stream.toList()) {
        Files.delete(file);
      }
    }
  }

  private UUID openRun(String runId) {
    return runs.saveAndFlush(
            new CatalogImportRun(runId, "OFFICIAL:etude.com", "0.1.0", null, null, NOW))
        .getId();
  }

  private static ObjectNode item(String itemKey, String productId) throws Exception {
    ObjectNode node = (ObjectNode) MAPPER.readTree(Files.readString(SAMPLE));
    if (itemKey == null) {
      node.remove("itemKey");
    } else {
      node.put("itemKey", itemKey);
    }
    node.put("sourceProductId", productId);
    node.put("name", "제품 " + productId);
    for (int i = 0; i < 2; i++) {
      ObjectNode color = (ObjectNode) node.path("shades").get(i).path("colors").get(0);
      String option = node.path("shades").get(i).path("sourceOptionId").asString();
      color.put("evidenceKey", productId + "/" + option + "/1");
    }
    return node;
  }

  private int count(String table) {
    return jdbc.queryForObject("select count(*) from " + table, Integer.class);
  }

  // --- 1. 확정된 결과를 실패 기록이 덮어쓰지 않는다 ---

  @Test
  void aFailureRecordNeverOverwritesAnItemAnotherRequestAlreadySettled() throws Exception {
    UUID run = openRun("run-race-1");
    JsonNode raw = item("000001", "p-1");
    ItemResult settled = service.importItem(run, raw);
    assertThat(settled.outcome()).isEqualTo(ImportItemOutcome.NEW);

    // 실패한 요청 A 가 뒤늦게 실패 기록을 남기려는 순간
    ItemResult late =
        service.recordFailure(
            run, CollectedProductReader.read(raw), new IllegalStateException("late"));

    assertThat(late.outcome()).isEqualTo(ImportItemOutcome.NEW);
    assertThat(late.productId()).isEqualTo(settled.productId());
    assertThat(late.colorsApplied()).isEqualTo(settled.colorsApplied());
    assertThat(late.duplicate()).isTrue();
    assertThat(
            jdbc.queryForObject(
                "select outcome from catalog_import_items where item_key = '000001'", String.class))
        .isEqualTo("NEW");
    assertThat(count("products")).isEqualTo(1);
  }

  // --- 2. itemKey 없는 틀린 줄이 이어받기를 막지 않는다 ---

  @Test
  void aLineWithoutItemKeyIsCountedApartAndDoesNotStopTheFileFromAdvancing() throws Exception {
    String header =
        "{\"runId\":\"run-race-2\",\"startedAt\":\"2026-11-08T21:30:00+09:00\","
            + "\"seed\":\"OFFICIAL:etude.com\",\"collectorVersion\":\"0.1.0\"}";
    ObjectNode bad = MAPPER.createObjectNode();
    bad.set("collected", item(null, "p-0"));
    ObjectNode good1 = MAPPER.createObjectNode();
    good1.put("itemKey", "000002");
    good1.set("collected", item("000002", "p-2"));
    ObjectNode good2 = MAPPER.createObjectNode();
    good2.put("itemKey", "000003");
    good2.set("collected", item("000003", "p-3"));
    Files.writeString(
        DIRECTORY.resolve("race.jsonl"),
        String.join(
                "\n",
                header,
                MAPPER.writeValueAsString(bad),
                MAPPER.writeValueAsString(good1),
                MAPPER.writeValueAsString(good2))
            + "\n",
        StandardCharsets.UTF_8);

    FileImportResult first = fileService.importFile("race.jsonl", 1, null);
    FileImportResult second = fileService.importFile("race.jsonl", 1, null);

    assertThat(first.processed()).isEqualTo(1);
    assertThat(first.unrecorded()).isEqualTo(1);
    assertThat(first.finished()).isFalse();
    assertThat(second.processed()).isEqualTo(1);
    assertThat(second.finished()).isFalse();
    FileImportResult third = fileService.importFile("race.jsonl", 1, null);
    assertThat(third.processed()).isZero();
    assertThat(third.unrecorded()).isEqualTo(1);
    assertThat(third.finished()).isTrue();
    assertThat(count("products")).isEqualTo(2);
    assertThat(count("catalog_import_items")).isEqualTo(2);
  }

  // --- 3. 실행은 진행 중인 건이 확정된 뒤에 끝난다 ---

  @Test
  void finishingARunWaitsForTheItemInFlightAndLaterItemsAreRefused() throws Exception {
    UUID run = openRun("run-race-3");
    CountDownLatch inPlan = new CountDownLatch(1);
    CountDownLatch release = new CountDownLatch(1);
    doAnswer(
            invocation -> {
              inPlan.countDown();
              release.await(30, TimeUnit.SECONDS);
              return invocation.callRealMethod();
            })
        .when(planner)
        .plan(org.mockito.ArgumentMatchers.any());
    ExecutorService pool = Executors.newFixedThreadPool(2);
    try {
      Future<ItemResult> inFlight =
          pool.submit(() -> service.importItem(run, item("000001", "p-1")));
      assertThat(inPlan.await(30, TimeUnit.SECONDS)).isTrue();

      Future<?> finishing = pool.submit(() -> runService.finish(run, ImportRunStatus.COMPLETED));
      assertThatThrownBy(() -> finishing.get(700, TimeUnit.MILLISECONDS))
          .isInstanceOf(TimeoutException.class);
      assertThat(runs.findById(run).orElseThrow().getStatus()).isEqualTo(ImportRunStatus.RUNNING);

      release.countDown();
      assertThat(inFlight.get(30, TimeUnit.SECONDS).outcome()).isEqualTo(ImportItemOutcome.NEW);
      finishing.get(30, TimeUnit.SECONDS);
    } catch (ExecutionException e) {
      throw new AssertionError(e);
    } finally {
      release.countDown();
      pool.shutdownNow();
    }

    // 완료 응답 시점에 이미 제품이 들어 있고, 그 뒤에는 새 건이 들어오지 못한다
    assertThat(runs.findById(run).orElseThrow().getStatus()).isEqualTo(ImportRunStatus.COMPLETED);
    assertThat(count("products")).isEqualTo(1);
    assertThatThrownBy(() -> service.importItem(run, item("000002", "p-2")))
        .isInstanceOf(CatalogImportRunClosedException.class);
    assertThat(count("products")).isEqualTo(1);
  }
}
