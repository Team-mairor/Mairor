package com.mairor.backend.products.imports;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.products.entity.CatalogImportRun;
import com.mairor.backend.products.entity.ImportItemOutcome;
import com.mairor.backend.products.imports.CatalogImportService.ItemResult;
import com.mairor.backend.products.repository.CatalogImportRunRepository;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.function.Consumer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/**
 * 수집 상품 한 건을 카탈로그에 반영하고 기록하는 흐름. 공유 샘플({@code etude_option_image.json})을 고쳐서 쓴다.
 *
 * <p>건마다 자기 트랜잭션으로 처리하므로 이 테스트는 트랜잭션으로 감싸지 않고 실제로 커밋시킨다. 그래서 테스트 전후에 표를 비운다. 설정은 판정 테스트와 같이 사진 색의
 * 품질 임계값을 0.8 로 정한 상태다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql,classpath:db/schema/executions.sql",
      "app.security.allowed-origins=http://localhost:3000",
      "catalog.color.min-quality.PRODUCT_PHOTO=0.8",
      "catalog.color.source-value-sites=OFFICIAL:etude.com"
    })
class CatalogImportServiceTest {

  private static final Path SAMPLE =
      Path.of("..", "shared", "catalog-import", "samples", "etude_option_image.json");
  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final Instant NOW = Instant.parse("2026-11-08T12:00:00Z");

  @Autowired private CatalogImportService service;
  @Autowired private CatalogImportRunRepository runs;
  @Autowired private JdbcTemplate jdbc;
  @MockitoSpyBean private CatalogMatchPlanner planner;
  @MockitoSpyBean private CatalogImportApplier applier;

  @BeforeEach
  void setUp() {
    clean();
    jdbc.update(
        "insert into product_categories (code, label, matchable, shade_selectable, sort_order)"
            + " values ('EYE', '아이', true, true, 3), ('SKINCARE', '스킨케어', false, false, 6)");
    jdbc.update(
        "insert into product_types (code, category_code, label, sort_order)"
            + " values ('MASCARA', 'EYE', '마스카라', 2), ('TONER', 'SKINCARE', '토너', 1)");
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

  private UUID openRun(String runId) {
    return runs.saveAndFlush(
            new CatalogImportRun(runId, "OFFICIAL:etude.com", "0.1.0", null, null, NOW))
        .getId();
  }

  private static ObjectNode item(Consumer<ObjectNode> change) throws Exception {
    ObjectNode node = (ObjectNode) MAPPER.readTree(Files.readString(SAMPLE));
    change.accept(node);
    return node;
  }

  private static ObjectNode color(ObjectNode product, int shadeIndex) {
    return (ObjectNode) product.path("shades").get(shadeIndex).path("colors").get(0);
  }

  private List<Map<String, Object>> slots() {
    return jdbc.queryForList(
        "select s.name as shade, c.sort_order, c.color_hex, c.review_status,"
            + " c.source_item_id::text as source_item_id, c.source_evidence_key"
            + " from product_shade_colors c join product_shades s on s.id = c.shade_id"
            + " order by s.sort_order, c.sort_order");
  }

  private int count(String table) {
    return jdbc.queryForObject("select count(*) from " + table, Integer.class);
  }

  // --- 새 제품 ---

  @Test
  void aNewItemCreatesTheProductShadesAndSlotsAndLinksEverySlotToItsItem() throws Exception {
    UUID run = openRun("run-1");

    ItemResult result = service.importItem(run, item(n -> {}));

    assertThat(result.outcome()).isEqualTo(ImportItemOutcome.NEW);
    assertThat(result.recorded()).isTrue();
    assertThat(result.duplicate()).isFalse();
    assertThat(result.colorsApplied()).isEqualTo(2);
    assertThat(result.productId()).isNotNull();
    assertThat(result.changedShadeIds()).hasSize(2);
    assertThat(count("products")).isEqualTo(1);
    assertThat(count("product_shades")).isEqualTo(2);
    String itemId =
        jdbc.queryForObject(
            "select id::text from catalog_import_items where item_key = '000003'", String.class);
    assertThat(slots())
        .extracting(
            r -> r.get("color_hex"),
            r -> r.get("review_status"),
            r -> r.get("source_item_id"),
            r -> r.get("source_evidence_key"))
        .containsExactly(
            org.assertj.core.groups.Tuple.tuple(
                "#1E1B1C", "AUTO_APPROVED", itemId, "example-curl-fix-mascara/01-black/1"),
            org.assertj.core.groups.Tuple.tuple(
                "#4A3427", "AUTO_APPROVED", itemId, "example-curl-fix-mascara/02-brown/1"));
    Map<String, Object> product = jdbc.queryForMap("select * from products");
    assertThat(product.get("source")).isEqualTo("OFFICIAL:etude.com");
    assertThat(product.get("source_product_id")).isEqualTo("example-curl-fix-mascara");
    assertThat(product.get("image_url")).isEqualTo("https://example.com/images/etude/main.png");
    assertThat(product.get("sale_status")).isEqualTo("ON_SALE");
    Map<String, Object> row = jdbc.queryForMap("select * from catalog_import_items");
    assertThat(row.get("outcome")).isEqualTo("NEW");
    assertThat(row.get("product_id").toString()).isEqualTo(result.productId().toString());
    assertThat(row.get("colors_applied")).isEqualTo(2);
  }

  @Test
  void anItemWithoutShadesCreatesJustTheProduct() throws Exception {
    UUID run = openRun("run-1");

    ItemResult result = service.importItem(run, item(n -> n.remove("shades")));

    assertThat(result.outcome()).isEqualTo(ImportItemOutcome.NEW);
    assertThat(result.colorsApplied()).isZero();
    assertThat(count("products")).isEqualTo(1);
    assertThat(count("product_shades")).isZero();
  }

  @Test
  void aProductInACategoryWithoutShadesIsCreatedWithoutThemAndSaysWhy() throws Exception {
    UUID run = openRun("run-1");

    ItemResult result =
        service.importItem(
            run,
            item(
                n -> {
                  n.put("categoryHint", "SKINCARE");
                  n.put("typeHint", "TONER");
                }));

    assertThat(result.outcome()).isEqualTo(ImportItemOutcome.NEW);
    assertThat(result.partial()).isTrue();
    assertThat(result.reasons()).contains(CatalogImportApplier.SHADES_NOT_SELECTABLE);
    assertThat(count("products")).isEqualTo(1);
    assertThat(count("product_shades")).isZero();
  }

  // --- 재전송과 갱신 ---

  @Test
  void resendingTheSameItemReturnsTheStoredResultAndChangesNothing() throws Exception {
    UUID run = openRun("run-1");
    ItemResult first = service.importItem(run, item(n -> {}));

    ItemResult again = service.importItem(run, item(n -> n.put("name", "다른 이름")));

    assertThat(again.duplicate()).isTrue();
    assertThat(again.outcome()).isEqualTo(ImportItemOutcome.NEW);
    assertThat(again.productId()).isEqualTo(first.productId());
    assertThat(again.changedShadeIds()).isEmpty();
    assertThat(count("catalog_import_items")).isEqualTo(1);
    assertThat(count("products")).isEqualTo(1);
    assertThat(jdbc.queryForObject("select name from products", String.class))
        .isNotEqualTo("다른 이름");
  }

  @Test
  void theSameItemSentAtTheSameTimeIsProcessedOnce() throws Exception {
    UUID run = openRun("run-1");
    ObjectNode node = item(n -> {});
    int threads = 4;
    ExecutorService pool = Executors.newFixedThreadPool(threads);
    CountDownLatch start = new CountDownLatch(1);
    List<Future<ItemResult>> futures = new ArrayList<>();
    for (int i = 0; i < threads; i++) {
      futures.add(
          pool.submit(
              () -> {
                start.await();
                return service.importItem(run, node);
              }));
    }
    start.countDown();
    List<ItemResult> results = new ArrayList<>();
    for (Future<ItemResult> future : futures) {
      results.add(future.get());
    }
    pool.shutdown();

    assertThat(results).filteredOn(r -> !r.duplicate()).hasSize(1);
    assertThat(results).allSatisfy(r -> assertThat(r.outcome()).isEqualTo(ImportItemOutcome.NEW));
    assertThat(count("catalog_import_items")).isEqualTo(1);
    assertThat(count("products")).isEqualTo(1);
    assertThat(count("product_shades")).isEqualTo(2);
  }

  @Test
  void collectingTheSameDataAgainInANewRunChangesNoColorAndKeepsTheOldSource() throws Exception {
    UUID first = openRun("run-1");
    service.importItem(first, item(n -> {}));
    String firstItemId =
        jdbc.queryForObject("select id::text from catalog_import_items", String.class);
    UUID second = openRun("run-2");

    ItemResult result = service.importItem(second, item(n -> {}));

    assertThat(result.outcome()).isEqualTo(ImportItemOutcome.UPDATE);
    assertThat(result.colorsApplied()).isZero();
    assertThat(result.changedShadeIds()).isEmpty();
    assertThat(count("products")).isEqualTo(1);
    assertThat(count("product_shades")).isEqualTo(2);
    assertThat(slots()).extracting(r -> r.get("source_item_id")).containsOnly(firstItemId);
  }

  @Test
  void aBetterNewerColorReplacesTheOldOneAndTheSlotPointsAtTheNewItem() throws Exception {
    UUID first = openRun("run-1");
    service.importItem(first, item(n -> {}));
    UUID second = openRun("run-2");

    ItemResult result =
        service.importItem(
            second,
            item(
                n -> {
                  n.put("itemKey", "000009");
                  n.put("collectedAt", "2026-11-06T10:32:00+09:00");
                  color(n, 0).put("hex", "#101010");
                }));

    assertThat(result.outcome()).isEqualTo(ImportItemOutcome.UPDATE);
    assertThat(result.colorsApplied()).isEqualTo(1);
    assertThat(result.reasons()).contains(ImportReason.COLOR_REPLACED.name());
    assertThat(result.changedShadeIds()).hasSize(1);
    String secondItemId =
        jdbc.queryForObject(
            "select id::text from catalog_import_items where item_key = '000009'", String.class);
    List<Map<String, Object>> slots = slots();
    assertThat(slots.get(0).get("color_hex")).isEqualTo("#101010");
    assertThat(slots.get(0).get("source_item_id")).isEqualTo(secondItemId);
    assertThat(slots.get(1).get("color_hex")).isEqualTo("#4A3427");
    assertThat(slots.get(1).get("source_item_id")).isNotEqualTo(secondItemId);
    assertThat(count("product_shade_colors")).isEqualTo(2);
  }

  @Test
  void aRenamedShadeKeepsItsIdentityAndItsSlots() throws Exception {
    UUID first = openRun("run-1");
    service.importItem(first, item(n -> {}));
    List<String> shadeIds =
        jdbc.queryForList("select id::text from product_shades order by sort_order", String.class);
    List<String> slotIds =
        jdbc.queryForList(
            "select c.id::text from product_shade_colors c join product_shades s on s.id = c.shade_id"
                + " order by s.sort_order",
            String.class);
    UUID second = openRun("run-2");

    ItemResult result =
        service.importItem(
            second,
            item(
                n -> {
                  n.put("itemKey", "000009");
                  ((ObjectNode) n.path("shades").get(0)).put("name", "01 딥 블랙");
                }));

    assertThat(result.outcome()).isEqualTo(ImportItemOutcome.UPDATE);
    assertThat(
            jdbc.queryForList("select name from product_shades order by sort_order", String.class))
        .contains("01 딥 블랙")
        .hasSize(2);
    assertThat(
            jdbc.queryForList(
                "select id::text from product_shades order by sort_order", String.class))
        .isEqualTo(shadeIds);
    assertThat(
            jdbc.queryForList(
                "select c.id::text from product_shade_colors c join product_shades s on s.id = c.shade_id"
                    + " order by s.sort_order",
                String.class))
        .isEqualTo(slotIds);
  }

  @Test
  void aShadeThatAppearsLaterIsAddedWithItsSourceOption() throws Exception {
    UUID first = openRun("run-1");
    service.importItem(first, item(n -> {}));
    UUID second = openRun("run-2");

    ItemResult result =
        service.importItem(
            second,
            item(
                n -> {
                  n.put("itemKey", "000009");
                  ObjectNode third = ((ObjectNode) n.path("shades").get(0)).deepCopy();
                  third.put("sourceOptionId", "03-navy");
                  third.put("name", "03 네이비");
                  third.put("sortOrder", 3);
                  ObjectNode slot = (ObjectNode) third.path("colors").get(0);
                  slot.put("hex", "#1B2A4A");
                  slot.put("evidenceKey", "example-curl-fix-mascara/03-navy/1");
                  ((ArrayNode) n.path("shades")).add(third);
                }));

    assertThat(result.outcome()).isEqualTo(ImportItemOutcome.UPDATE);
    assertThat(result.colorsApplied()).isEqualTo(1);
    assertThat(count("product_shades")).isEqualTo(3);
    assertThat(
            jdbc.queryForObject(
                "select source_option_id from product_shades where name = '03 네이비'", String.class))
        .isEqualTo("03-navy");
    assertThat(slots()).hasSize(3);
  }

  @Test
  void anOlderCollectionIsRecordedAsStaleAndChangesNothing() throws Exception {
    UUID first = openRun("run-1");
    service.importItem(first, item(n -> {}));
    UUID second = openRun("run-2");

    ItemResult result =
        service.importItem(
            second,
            item(
                n -> {
                  n.put("itemKey", "000009");
                  n.put("collectedAt", "2026-11-01T10:32:00+09:00");
                  n.put("name", "예전 이름");
                  color(n, 0).put("hex", "#101010");
                }));

    assertThat(result.outcome()).isEqualTo(ImportItemOutcome.STALE);
    assertThat(result.productId()).isNull();
    assertThat(result.colorsApplied()).isZero();
    assertThat(jdbc.queryForObject("select name from products", String.class))
        .isNotEqualTo("예전 이름");
    assertThat(slots().get(0).get("color_hex")).isEqualTo("#1E1B1C");
  }

  @Test
  void anUnclassifiableItemIsRecordedAndNothingIsCreated() throws Exception {
    UUID run = openRun("run-1");

    ItemResult result =
        service.importItem(
            run,
            item(
                n -> {
                  n.put("typeHint", "NO_SUCH_TYPE");
                  n.remove("categoryHint");
                }));

    assertThat(result.outcome()).isEqualTo(ImportItemOutcome.UNCLASSIFIED);
    assertThat(count("products")).isZero();
    assertThat(count("catalog_import_items")).isEqualTo(1);
  }

  // --- 틀린 건과 실패한 건 ---

  @Test
  void anInvalidItemIsRecordedWithItsIssuesAndNothingElseHappens() throws Exception {
    UUID run = openRun("run-1");

    ItemResult result = service.importItem(run, item(n -> n.remove("sourceProductId")));

    assertThat(result.outcome()).isEqualTo(ImportItemOutcome.INVALID);
    assertThat(result.recorded()).isTrue();
    assertThat(result.reasons()).contains("REQUIRED");
    assertThat(count("products")).isZero();
    Map<String, Object> row = jdbc.queryForMap("select * from catalog_import_items");
    assertThat(row.get("outcome")).isEqualTo("INVALID");
    assertThat(row.get("message").toString()).contains("sourceProductId");
  }

  @Test
  void anItemWithoutAnItemKeyCannotBeRecorded() throws Exception {
    UUID run = openRun("run-1");

    ItemResult result = service.importItem(run, item(n -> n.remove("itemKey")));

    assertThat(result.outcome()).isEqualTo(ImportItemOutcome.INVALID);
    assertThat(result.recorded()).isFalse();
    assertThat(result.itemKey()).isNull();
    assertThat(count("catalog_import_items")).isZero();
  }

  @Test
  void aFailureRollsBackThatItemOnlyAndIsRecordedAsFailed() throws Exception {
    UUID run = openRun("run-1");
    // 반영을 끝까지 한 뒤에 터지면 제품·호수·칸이 모두 되돌려져야 한다
    doAnswer(
            invocation -> {
              invocation.callRealMethod();
              throw new IllegalStateException("boom");
            })
        .doCallRealMethod()
        .when(applier)
        .apply(any(), any());

    ItemResult failed = service.importItem(run, item(n -> n.put("itemKey", "000001")));
    ItemResult next =
        service.importItem(
            run,
            item(
                n -> {
                  n.put("itemKey", "000002");
                  n.put("sourceProductId", "other-product");
                  n.put("name", "다른 제품");
                  // 칸의 근거 키는 <상품 번호>/<옵션 값>/<칸 순서> 꼴이라 상품 번호를 따라간다
                  color(n, 0).put("evidenceKey", "other-product/01-black/1");
                  color(n, 1).put("evidenceKey", "other-product/02-brown/1");
                }));

    assertThat(failed.outcome()).isEqualTo(ImportItemOutcome.FAILED);
    assertThat(failed.recorded()).isTrue();
    assertThat(failed.productId()).isNull();
    assertThat(next.outcome()).isEqualTo(ImportItemOutcome.NEW);
    assertThat(count("products")).isEqualTo(1);
    assertThat(jdbc.queryForObject("select source_product_id from products", String.class))
        .isEqualTo("other-product");
    Map<String, Object> row =
        jdbc.queryForMap("select * from catalog_import_items where item_key = '000001'");
    assertThat(row.get("outcome")).isEqualTo("FAILED");
    assertThat(row.get("message").toString()).contains("IllegalStateException").contains("boom");
    assertThat(row.get("product_id")).isNull();
  }

  @Test
  void aPlanningErrorIsAlsoRecordedAsFailedWithoutSpoilingTheNextItem() throws Exception {
    UUID run = openRun("run-1");
    doThrow(new IllegalStateException("plan boom")).doCallRealMethod().when(planner).plan(any());

    ItemResult failed = service.importItem(run, item(n -> n.put("itemKey", "000001")));
    ItemResult next = service.importItem(run, item(n -> n.put("itemKey", "000002")));

    assertThat(failed.outcome()).isEqualTo(ImportItemOutcome.FAILED);
    assertThat(next.outcome()).isEqualTo(ImportItemOutcome.NEW);
    assertThat(count("catalog_import_items")).isEqualTo(2);
  }

  // --- 실행 상태 ---

  @Test
  void anItemCannotBeAddedToAFinishedOrMissingRun() throws Exception {
    UUID run = openRun("run-1");
    CatalogImportRun entity = runs.findById(run).orElseThrow();
    entity.complete(NOW.plusSeconds(1));
    runs.saveAndFlush(entity);

    assertThatThrownBy(() -> service.importItem(run, item(n -> {})))
        .isInstanceOf(CatalogImportRunClosedException.class);
    assertThatThrownBy(() -> service.importItem(UUID.randomUUID(), item(n -> {})))
        .isInstanceOf(CatalogImportRunNotFoundException.class);
    assertThat(count("catalog_import_items")).isZero();
    assertThat(count("products")).isZero();
  }

  @Test
  void theItemsArrayShapeIsNotRequiredForASingleItem() throws Exception {
    // 한 건 처리는 배열이 아니라 건 객체 하나를 받는다
    UUID run = openRun("run-1");
    ArrayNode notAnObject = MAPPER.createArrayNode();

    ItemResult result = service.importItem(run, notAnObject);

    assertThat(result.outcome()).isEqualTo(ImportItemOutcome.INVALID);
    assertThat(result.recorded()).isFalse();
  }
}
