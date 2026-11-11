package com.mairor.backend.products.imports;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.products.entity.ImportItemOutcome;
import com.mairor.backend.products.imports.CatalogImportRunService.RunView;
import com.mairor.backend.products.imports.CatalogImportRunService.StartCommand;
import com.mairor.backend.products.imports.CatalogImportStatsService.Quality;
import com.mairor.backend.products.imports.CatalogImportStatsService.RunStats;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
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
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/**
 * 적재 통계. 실행 통계(그 실행이 한 일)와 현재 품질 통계(지금 카탈로그의 색 상태)를 따로 확인한다. 건마다 자기 트랜잭션으로 처리하므로 이 테스트는 트랜잭션으로 감싸지
 * 않고 실제로 커밋시킨다. 그래서 테스트 전후에 표를 비운다. 사진 색의 품질 임계값은 0.8 이다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql",
      "app.security.allowed-origins=http://localhost:3000",
      "catalog.color.min-quality.PRODUCT_PHOTO=0.8"
    })
class CatalogImportStatsTest {

  private static final Path SAMPLE =
      Path.of("..", "shared", "catalog-import", "samples", "etude_option_image.json");
  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final Instant START = Instant.parse("2026-11-08T12:00:00Z");

  @Autowired private CatalogImportRunService runs;
  @Autowired private CatalogImportStatsService stats;
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

  private RunView open(String runId) {
    return runs.start(new StartCommand(runId, "OFFICIAL:etude.com", "0.1.0", START, null));
  }

  private static ObjectNode item(Consumer<ObjectNode> change) throws Exception {
    ObjectNode node = (ObjectNode) MAPPER.readTree(Files.readString(SAMPLE));
    change.accept(node);
    return node;
  }

  private static ObjectNode color(ObjectNode product, int shadeIndex) {
    return (ObjectNode) product.path("shades").get(shadeIndex).path("colors").get(0);
  }

  private void send(UUID run, ObjectNode... items) {
    ArrayNode array = MAPPER.createArrayNode();
    for (ObjectNode item : items) {
      array.add(item);
    }
    runs.importBatch(run, array);
  }

  /** 다른 제품. 상품 번호를 바꾸면 칸의 근거 키도 그 번호를 따라간다. */
  private static ObjectNode other(String itemKey, String productId, Consumer<ObjectNode> change)
      throws Exception {
    return item(
        n -> {
          n.put("itemKey", itemKey);
          n.put("sourceProductId", productId);
          n.put("name", "제품 " + productId);
          color(n, 0).put("evidenceKey", productId + "/01-black/1");
          color(n, 1).put("evidenceKey", productId + "/02-brown/1");
          change.accept(n);
        });
  }

  // --- 실행 통계 ---

  @Test
  void runStatsCountEveryOutcomeAndKeepFailuresVisibleEvenWhenTheRunCompletes() throws Exception {
    RunView run = open("run-1");
    ObjectNode invalid = item(n -> n.put("itemKey", "000004"));
    invalid.remove("sourceProductId");
    send(
        run.id(),
        item(n -> n.put("itemKey", "000001")),
        other("000002", "p-2", n -> {}),
        other(
            "000003",
            "p-3",
            n -> {
              n.put("typeHint", "NO_SUCH_TYPE");
              n.remove("categoryHint");
            }),
        invalid);
    runs.finish(run.id(), com.mairor.backend.products.entity.ImportRunStatus.COMPLETED);

    RunStats result = stats.runStats(run.id());

    assertThat(result.run().status().name()).isEqualTo("COMPLETED");
    assertThat(result.total()).isEqualTo(4);
    assertThat(result.byOutcome())
        .containsEntry(ImportItemOutcome.NEW, 2)
        .containsEntry(ImportItemOutcome.UNCLASSIFIED, 1)
        .containsEntry(ImportItemOutcome.INVALID, 1)
        .containsEntry(ImportItemOutcome.UPDATE, 0)
        .containsEntry(ImportItemOutcome.FAILED, 0);
    assertThat(result.byOutcome()).hasSize(ImportItemOutcome.values().length);
    assertThat(result.created()).isEqualTo(2);
    assertThat(result.updated()).isZero();
    assertThat(result.skipped()).isEqualTo(1);
    assertThat(result.failed()).isEqualTo(1);
    assertThat(result.colorsApplied()).isEqualTo(4);
    assertThat(result.reasons()).containsEntry("REQUIRED", 1);
    assertThat(result.problemCount()).isEqualTo(1);
    assertThat(result.problems())
        .singleElement()
        .satisfies(
            p -> {
              assertThat(p.itemKey()).isEqualTo("000004");
              assertThat(p.outcome()).isEqualTo(ImportItemOutcome.INVALID);
              assertThat(p.message()).contains("sourceProductId");
            });
  }

  @Test
  void aSecondRunIsCountedSeparatelyFromTheFirst() throws Exception {
    RunView first = open("run-1");
    send(first.id(), item(n -> n.put("itemKey", "000001")));
    RunView second = open("run-2");
    send(second.id(), item(n -> n.put("itemKey", "000009")));

    assertThat(stats.runStats(first.id()).created()).isEqualTo(1);
    RunStats result = stats.runStats(second.id());
    assertThat(result.created()).isZero();
    assertThat(result.updated()).isEqualTo(1);
    assertThat(result.colorsApplied()).isZero();
    assertThat(result.partial()).isZero();
  }

  @Test
  void problemsAreCappedButTheirTotalIsExact() throws Exception {
    RunView run = open("run-1");
    int count = CatalogImportStatsService.MAX_PROBLEMS + 5;
    for (int start = 0; start < count; start += 25) {
      ArrayNode batch = MAPPER.createArrayNode();
      for (int i = start; i < Math.min(start + 25, count); i++) {
        ObjectNode bad = item(n -> {});
        bad.put("itemKey", String.format("%06d", i));
        bad.remove("sourceProductId");
        batch.add(bad);
      }
      runs.importBatch(run.id(), batch);
    }

    RunStats result = stats.runStats(run.id());

    assertThat(result.failed()).isEqualTo(count);
    assertThat(result.problemCount()).isEqualTo(count);
    assertThat(result.problems()).hasSize(CatalogImportStatsService.MAX_PROBLEMS);
    assertThat(result.problems().get(0).itemKey()).isEqualTo("000000");
  }

  @Test
  void anEmptyRunHasZeroEverythingAndAnUnknownRunIsNotFound() {
    RunView run = open("run-1");

    RunStats result = stats.runStats(run.id());

    assertThat(result.total()).isZero();
    assertThat(result.colorsApplied()).isZero();
    assertThat(result.reasons()).isEmpty();
    assertThat(result.problems()).isEmpty();
    assertThatThrownBy(() -> stats.runStats(UUID.randomUUID()))
        .isInstanceOf(CatalogImportRunNotFoundException.class);
  }

  // --- 현재 품질 통계 ---

  @Test
  void anEmptyCatalogHasZeroCountsAndNoRatios() {
    Quality quality = stats.quality(null);

    assertThat(quality.products()).isZero();
    assertThat(quality.shades().total()).isZero();
    assertThat(quality.shades().usableRatio()).isNull();
    assertThat(quality.slots().total()).isZero();
    assertThat(quality.usableBySource()).isEmpty();
  }

  @Test
  void qualitySeparatesUsableBelowThresholdAndMissingColors() throws Exception {
    RunView run = open("run-1");
    send(
        run.id(),
        // 제품 A: 두 호수 모두 사용 가능
        other("000001", "a", n -> {}),
        // 제품 B: 한 호수는 기준 미달 품질, 다른 호수는 색을 못 찾음
        other(
            "000002",
            "b",
            n -> {
              color(n, 0).put("colorQuality", 0.5);
              ObjectNode second = (ObjectNode) n.path("shades").get(1);
              second.put("colorStatus", "NOT_FOUND");
              ObjectNode slot = color(n, 1);
              slot.remove("hex");
              slot.remove("colorSource");
              slot.remove("shadeLink");
              slot.remove("colorQuality");
            }),
        // 제품 C: 호수가 없다
        other("000003", "c", n -> n.remove("shades")));

    Quality quality = stats.quality(null);

    assertThat(quality.products()).isEqualTo(3);
    assertThat(quality.slots().total()).isEqualTo(4);
    assertThat(quality.slots().usable()).isEqualTo(2);
    assertThat(quality.slots().belowThreshold()).isEqualTo(1);
    assertThat(quality.slots().withoutColor()).isEqualTo(1);
    assertThat(quality.slots().usableRatio()).isEqualTo(0.5);
    assertThat(quality.shades().total()).isEqualTo(4);
    assertThat(quality.shades().usable()).isEqualTo(2);
    assertThat(quality.shades().belowThreshold()).isEqualTo(1);
    assertThat(quality.shades().withoutColor()).isEqualTo(1);
    assertThat(quality.shades().usableRatio()).isEqualTo(0.5);
    assertThat(quality.shades().belowThresholdRatio()).isEqualTo(0.25);
    assertThat(quality.usableBySource()).containsEntry("PRODUCT_PHOTO", 2);
  }

  @Test
  void aShadeWithoutAnySlotCountsAsWithoutColor() throws Exception {
    RunView run = open("run-1");
    send(run.id(), other("000001", "a", n -> {}));
    jdbc.update(
        "insert into product_shades (id, product_id, name, name_normalized, sort_order,"
            + " created_at, updated_at) select gen_random_uuid(), id, '칸 없는 호수', '칸 없는 호수', 9,"
            + " now(), now() from products");

    Quality quality = stats.quality(null);

    assertThat(quality.shades().total()).isEqualTo(3);
    assertThat(quality.shades().withoutColor()).isEqualTo(1);
    assertThat(quality.slots().total()).isEqualTo(2);
  }

  @Test
  void qualityCanBeLimitedToOneSource() throws Exception {
    RunView run = open("run-1");
    send(run.id(), other("000001", "a", n -> {}));
    jdbc.update(
        "update products set source = 'OFFICIAL:other.example' where source_product_id = 'a'");
    send(
        run.id(),
        other(
            "000002",
            "b",
            n -> {
              color(n, 0).put("colorQuality", 0.5);
              color(n, 1).put("colorQuality", 0.5);
            }));

    Quality all = stats.quality(null);
    Quality etude = stats.quality("OFFICIAL:etude.com");
    Quality other = stats.quality("OFFICIAL:other.example");
    Quality none = stats.quality("OFFICIAL:nowhere.example");

    assertThat(all.products()).isEqualTo(2);
    assertThat(all.slots().usable()).isEqualTo(2);
    assertThat(etude.source()).isEqualTo("OFFICIAL:etude.com");
    assertThat(etude.products()).isEqualTo(1);
    assertThat(etude.slots().usable()).isZero();
    assertThat(etude.slots().belowThreshold()).isEqualTo(2);
    assertThat(other.slots().usable()).isEqualTo(2);
    assertThat(other.usableBySource()).containsEntry("PRODUCT_PHOTO", 2);
    assertThat(none.products()).isZero();
    assertThat(none.slots().usableRatio()).isNull();
  }

  @Test
  void qualityFollowsTheCurrentStateWhenAColorIsDowngradedLater() throws Exception {
    RunView run = open("run-1");
    send(run.id(), other("000001", "a", n -> {}));
    assertThat(stats.quality(null).slots().usable()).isEqualTo(2);

    jdbc.update("update product_shade_colors set review_status = 'BELOW_THRESHOLD'");

    Quality after = stats.quality(null);
    assertThat(after.slots().usable()).isZero();
    assertThat(after.slots().belowThreshold()).isEqualTo(2);
    assertThat(after.usableBySource()).isEmpty();
  }
}
