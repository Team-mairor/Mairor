package com.mairor.backend.products.imports;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doCallRealMethod;
import static org.mockito.Mockito.doThrow;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.products.entity.ImportItemOutcome;
import com.mairor.backend.products.entity.ImportRunStatus;
import com.mairor.backend.products.imports.CatalogEvidenceService.Evidence;
import com.mairor.backend.products.imports.CatalogImportFileService.FileImportResult;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.UUID;
import java.util.function.Consumer;
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
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/**
 * 실행 결과 파일을 읽어 적재하는 흐름: 끝까지 적재, 나눠서 적재(이어 받기), 끊긴 줄 처리, 틀린 건 재처리, 근거 조회. 폴더는 테스트마다 임시 폴더다. 건마다 자기
 * 트랜잭션으로 처리하므로 이 테스트는 트랜잭션으로 감싸지 않고 실제로 커밋시킨다. 그래서 테스트 전후에 표를 비운다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql",
      "app.security.allowed-origins=http://localhost:3000",
      "catalog.color.min-quality.PRODUCT_PHOTO=0.8"
    })
class CatalogImportFileServiceTest {

  private static final Path SAMPLE =
      Path.of("..", "shared", "catalog-import", "samples", "etude_option_image.json");
  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final Path DIRECTORY = newDirectory();

  private static Path newDirectory() {
    try {
      return Files.createTempDirectory("catalog-runs-test");
    } catch (IOException e) {
      throw new IllegalStateException(e);
    }
  }

  @DynamicPropertySource
  static void directory(DynamicPropertyRegistry registry) {
    registry.add("catalog.import.result-dir", DIRECTORY::toString);
  }

  @Autowired private CatalogImportFileService files;
  @Autowired private CatalogEvidenceService evidence;
  @Autowired private CatalogImportRunService runs;
  @Autowired private JdbcTemplate jdbc;
  @MockitoSpyBean private CatalogMatchPlanner planner;

  @BeforeEach
  void setUp() throws IOException {
    clean();
    jdbc.update(
        "insert into product_categories (code, label, matchable, shade_selectable, sort_order)"
            + " values ('EYE', '아이', true, true, 3)");
    jdbc.update(
        "insert into product_types (code, category_code, label, sort_order)"
            + " values ('MASCARA', 'EYE', '마스카라', 2)");
  }

  @AfterEach
  void tearDown() throws IOException {
    clean();
  }

  private void clean() throws IOException {
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

  private static ObjectNode product(String productId, Consumer<ObjectNode> change)
      throws Exception {
    ObjectNode node = (ObjectNode) MAPPER.readTree(Files.readString(SAMPLE));
    node.put("sourceProductId", productId);
    node.put("name", "제품 " + productId);
    for (int i = 0; i < 2; i++) {
      ObjectNode color = (ObjectNode) node.path("shades").get(i).path("colors").get(0);
      String option = node.path("shades").get(i).path("sourceOptionId").asString();
      color.put("evidenceKey", productId + "/" + option + "/1");
    }
    change.accept(node);
    return node;
  }

  /** 건 한 줄: 수집기가 쓰는 {itemKey, collected, evidence[], raw} 모양이다. */
  private static String line(String itemKey, ObjectNode collected) throws Exception {
    collected.put("itemKey", itemKey);
    ObjectNode row = MAPPER.createObjectNode();
    row.put("itemKey", itemKey);
    row.set("collected", collected);
    ArrayNode evidence = row.putArray("evidence");
    for (var shade : collected.path("shades")) {
      ObjectNode record = evidence.addObject();
      record.put("evidenceKey", shade.path("colors").get(0).path("evidenceKey").asString());
      record.put("imageUrl", "https://example.com/" + itemKey + ".png");
      record.put("method", "pixel_median_lab");
      record.putObject("scores").put("homogeneity", 0.95);
    }
    row.putObject("raw");
    return MAPPER.writeValueAsString(row);
  }

  private Path file(String name, String runId, String... lines) throws IOException {
    String header =
        "{\"runId\":\""
            + runId
            + "\",\"startedAt\":\"2026-11-08T21:30:00+09:00\","
            + "\"seed\":\"OFFICIAL:etude.com\",\"collectorVersion\":\"0.1.0\"}";
    Path path = DIRECTORY.resolve(name);
    Files.writeString(
        path, header + "\n" + String.join("\n", lines) + "\n", StandardCharsets.UTF_8);
    return path;
  }

  private int count(String table) {
    return jdbc.queryForObject("select count(*) from " + table, Integer.class);
  }

  // --- 끝까지 적재 ---

  @Test
  void aWholeFileIsImportedAndTheRunIsCompleted() throws Exception {
    file(
        "a.jsonl",
        "run-a",
        line("000001", product("p-1", n -> {})),
        line("000002", product("p-2", n -> {})),
        line("000003", product("p-3", n -> {})));

    FileImportResult result = files.importFile("a.jsonl", null, null);

    assertThat(result.finished()).isTrue();
    assertThat(result.processed()).isEqualTo(3);
    assertThat(result.unreadable()).isZero();
    assertThat(result.run().status()).isEqualTo(ImportRunStatus.COMPLETED);
    assertThat(result.stats().created()).isEqualTo(3);
    assertThat(result.stats().colorsApplied()).isEqualTo(6);
    assertThat(count("products")).isEqualTo(3);
    assertThat(
            jdbc.queryForObject(
                "select result_file from catalog_import_runs where run_id = 'run-a'", String.class))
        .isEqualTo("a.jsonl");
  }

  @Test
  void aBigFileIsImportedInPartsAndEachCallContinuesWhereTheLastStopped() throws Exception {
    file(
        "b.jsonl",
        "run-b",
        line("000001", product("p-1", n -> {})),
        line("000002", product("p-2", n -> {})),
        line("000003", product("p-3", n -> {})));

    FileImportResult first = files.importFile("b.jsonl", 2, null);
    FileImportResult second = files.importFile("b.jsonl", 2, null);
    FileImportResult third = files.importFile("b.jsonl", 2, null);

    assertThat(first.processed()).isEqualTo(2);
    assertThat(first.finished()).isFalse();
    assertThat(first.run().status()).isEqualTo(ImportRunStatus.RUNNING);
    assertThat(second.processed()).isEqualTo(1);
    assertThat(second.finished()).isTrue();
    assertThat(second.run().status()).isEqualTo(ImportRunStatus.COMPLETED);
    assertThat(third.processed()).isZero();
    assertThat(third.finished()).isTrue();
    assertThat(count("products")).isEqualTo(3);
    assertThat(count("catalog_import_items")).isEqualTo(3);
    assertThat(count("catalog_import_runs")).isEqualTo(1);
  }

  @Test
  void aCutOffTailIsIgnoredAndABrokenMiddleLineIsCountedNotImported() throws Exception {
    Path path =
        file(
            "c.jsonl",
            "run-c",
            line("000001", product("p-1", n -> {})),
            "{ this line is broken",
            line("000002", product("p-2", n -> {})));
    Files.writeString(
        path,
        "{\"itemKey\":\"000003\",\"collected\":{\"itemKe",
        StandardCharsets.UTF_8,
        java.nio.file.StandardOpenOption.APPEND);

    FileImportResult result = files.importFile("c.jsonl", null, null);

    assertThat(result.finished()).isTrue();
    assertThat(result.processed()).isEqualTo(2);
    assertThat(result.unreadable()).isEqualTo(1);
    assertThat(count("catalog_import_items")).isEqualTo(2);
  }

  @Test
  void aLineWithoutACollectedObjectIsUnreadable() throws Exception {
    file("d.jsonl", "run-d", "{\"itemKey\":\"000001\"}", line("000002", product("p-2", n -> {})));

    FileImportResult result = files.importFile("d.jsonl", null, null);

    assertThat(result.processed()).isEqualTo(1);
    assertThat(result.unreadable()).isEqualTo(1);
  }

  @Test
  void badRequestsAreRejectedBeforeAnythingIsImported() throws Exception {
    file("e.jsonl", "run-e", line("000001", product("p-1", n -> {})));

    assertThatThrownBy(() -> files.importFile("missing.jsonl", null, null))
        .isInstanceOfSatisfying(
            BusinessException.class,
            e -> assertThat(e.code()).isEqualTo(CatalogRunFileReader.FILE_NOT_FOUND));
    assertThatThrownBy(() -> files.importFile("../e.jsonl", null, null))
        .isInstanceOfSatisfying(
            BusinessException.class,
            e -> assertThat(e.code()).isEqualTo(CatalogRunFileReader.INVALID_FILE));
    for (int limit : new int[] {0, -1, CatalogImportFileService.MAX_LIMIT + 1}) {
      assertThatThrownBy(() -> files.importFile("e.jsonl", limit, null))
          .isInstanceOfSatisfying(
              BusinessException.class, e -> assertThat(e.code()).isEqualTo("VALIDATION_FAILED"));
    }
    assertThat(count("catalog_import_runs")).isZero();
  }

  @Test
  void aRunThatTheCollectorAlreadyFailedCannotBeContinuedFromTheFile() throws Exception {
    file("f.jsonl", "run-f", line("000001", product("p-1", n -> {})));
    UUID id =
        runs.start(new CatalogImportRunService.StartCommand("run-f", null, null, null, "f.jsonl"))
            .id();
    runs.finish(id, ImportRunStatus.FAILED);

    assertThatThrownBy(() -> files.importFile("f.jsonl", null, null))
        .isInstanceOf(CatalogImportRunClosedException.class);
    assertThat(count("catalog_import_items")).isZero();
  }

  // --- 틀린 건 재처리 ---

  @Test
  void onlyTheFailedItemsOfAnEarlierRunAreProcessedAgainInANewRun() throws Exception {
    file(
        "g.jsonl",
        "run-g",
        line("000001", product("p-1", n -> {})),
        line("000002", product("p-2", n -> {})),
        line("000003", product("p-3", n -> n.remove("sourceProductId"))));
    // 첫 건은 서버 쪽 일시 오류로 실패하고 나머지는 정상 처리된다
    doThrow(new IllegalStateException("temporary")).doCallRealMethod().when(planner).plan(any());
    FileImportResult first = files.importFile("g.jsonl", null, null);
    doCallRealMethod().when(planner).plan(any());

    assertThat(first.stats().byOutcome())
        .containsEntry(ImportItemOutcome.FAILED, 1)
        .containsEntry(ImportItemOutcome.NEW, 1)
        .containsEntry(ImportItemOutcome.INVALID, 1);

    FileImportResult retry = files.importFile("g.jsonl", null, first.run().id());

    assertThat(retry.run().runId()).isEqualTo("run-g-retry");
    assertThat(retry.run().id()).isNotEqualTo(first.run().id());
    assertThat(retry.finished()).isTrue();
    assertThat(retry.processed()).isEqualTo(2);
    // 다시 처리한 건: 일시 오류였던 건은 반영되고, 형식이 틀린 건은 여전히 틀리다
    assertThat(retry.stats().byOutcome())
        .containsEntry(ImportItemOutcome.NEW, 1)
        .containsEntry(ImportItemOutcome.INVALID, 1);
    assertThat(count("products")).isEqualTo(2);
    // 이전 실행의 기록은 그대로 남는다
    assertThat(runs.get(first.run().id()).status()).isEqualTo(ImportRunStatus.COMPLETED);
    assertThat(
            jdbc.queryForObject(
                "select count(*) from catalog_import_items i join catalog_import_runs r"
                    + " on r.id = i.run_id where r.run_id = 'run-g' and i.outcome = 'FAILED'",
                Integer.class))
        .isEqualTo(1);
  }

  @Test
  void retryingTwiceDoesNothingTheSecondTime() throws Exception {
    file("h.jsonl", "run-h", line("000001", product("p-1", n -> n.remove("sourceProductId"))));
    FileImportResult first = files.importFile("h.jsonl", null, null);

    FileImportResult once = files.importFile("h.jsonl", null, first.run().id());
    FileImportResult again = files.importFile("h.jsonl", null, first.run().id());

    assertThat(once.processed()).isEqualTo(1);
    assertThat(again.processed()).isZero();
    assertThat(again.finished()).isTrue();
    assertThat(count("catalog_import_runs")).isEqualTo(2);
  }

  @Test
  void aRetryNeedsTheSameFileAndAnExistingRun() throws Exception {
    file("i.jsonl", "run-i", line("000001", product("p-1", n -> n.remove("sourceProductId"))));
    file("j.jsonl", "run-j", line("000001", product("p-1", n -> {})));
    FileImportResult first = files.importFile("i.jsonl", null, null);

    assertThatThrownBy(() -> files.importFile("j.jsonl", null, first.run().id()))
        .isInstanceOfSatisfying(
            BusinessException.class, e -> assertThat(e.code()).isEqualTo("RETRY_FILE_MISMATCH"));
    assertThatThrownBy(() -> files.importFile("i.jsonl", null, UUID.randomUUID()))
        .isInstanceOf(CatalogImportRunNotFoundException.class);
  }

  // --- 근거 조회 ---

  private UUID slotId(String productId, String option) {
    return UUID.fromString(
        jdbc.queryForObject(
            "select c.id::text from product_shade_colors c" + " where c.source_evidence_key = ?",
            String.class,
            productId + "/" + option + "/1"));
  }

  @Test
  void aSlotsEvidenceIsFoundInTheFileThroughItsItemAndKey() throws Exception {
    file("k.jsonl", "run-k", line("000007", product("p-7", n -> {})));
    files.importFile("k.jsonl", null, null);

    Evidence found = evidence.find(slotId("p-7", "01-black"));

    assertThat(found.itemKey()).isEqualTo("000007");
    assertThat(found.runId()).isEqualTo("run-k");
    assertThat(found.resultFile()).isEqualTo("k.jsonl");
    assertThat(found.evidenceKey()).isEqualTo("p-7/01-black/1");
    assertThat(found.fileAvailable()).isTrue();
    assertThat(found.evidence().path("method").asString()).isEqualTo("pixel_median_lab");
    assertThat(found.evidence().path("imageUrl").asString()).contains("000007");
  }

  @Test
  void whenTheFileIsGoneTheAnswerSaysSoInsteadOfFailing() throws Exception {
    Path path = file("l.jsonl", "run-l", line("000001", product("p-1", n -> {})));
    files.importFile("l.jsonl", null, null);
    Files.delete(path);

    Evidence found = evidence.find(slotId("p-1", "01-black"));

    assertThat(found.fileAvailable()).isFalse();
    assertThat(found.evidence()).isNull();
    assertThat(found.itemKey()).isEqualTo("000001");
  }

  @Test
  void aRunOpenedWithoutAFileHasNoEvidenceToLookUp() throws Exception {
    UUID id =
        runs.start(new CatalogImportRunService.StartCommand("run-m", null, null, null, null)).id();
    ArrayNode batch = MAPPER.createArrayNode();
    batch.add(product("p-1", n -> n.put("itemKey", "000001")));
    runs.importBatch(id, batch);

    Evidence found = evidence.find(slotId("p-1", "01-black"));

    assertThat(found.resultFile()).isNull();
    assertThat(found.fileAvailable()).isFalse();
    assertThat(found.evidence()).isNull();
  }

  @Test
  void aSlotNotMadeByAnImportOrUnknownHasNothingToLookUp() throws Exception {
    file("n.jsonl", "run-n", line("000001", product("p-1", n -> {})));
    files.importFile("n.jsonl", null, null);
    jdbc.update(
        "update product_shade_colors set source_item_id = null, source_evidence_key = null");
    UUID slot =
        UUID.fromString(
            jdbc.queryForObject("select id::text from product_shade_colors limit 1", String.class));

    assertThatThrownBy(() -> evidence.find(slot))
        .isInstanceOfSatisfying(
            BusinessException.class,
            e -> assertThat(e.code()).isEqualTo(CatalogEvidenceService.EVIDENCE_NOT_RECORDED));
    assertThatThrownBy(() -> evidence.find(UUID.randomUUID()))
        .isInstanceOfSatisfying(
            BusinessException.class,
            e -> assertThat(e.code()).isEqualTo(CatalogEvidenceService.COLOR_NOT_FOUND));
  }
}
