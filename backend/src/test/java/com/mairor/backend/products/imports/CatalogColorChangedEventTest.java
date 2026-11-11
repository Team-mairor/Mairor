package com.mairor.backend.products.imports;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.products.entity.CatalogImportRun;
import com.mairor.backend.products.entity.ColorSource;
import com.mairor.backend.products.entity.ImportItemOutcome;
import com.mairor.backend.products.entity.NameSource;
import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductShadeColor;
import com.mairor.backend.products.entity.ProductType;
import com.mairor.backend.products.entity.ReviewStatus;
import com.mairor.backend.products.event.CatalogColorChanged;
import com.mairor.backend.products.imports.CatalogImportService.ItemResult;
import com.mairor.backend.products.repository.CatalogImportRunRepository;
import com.mairor.backend.products.repository.ProductRepository;
import com.mairor.backend.products.repository.ProductTypeRepository;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.Consumer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Import;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

/**
 * 서비스에 보이는 색이 바뀌면 {@link CatalogColorChanged}가 같은 트랜잭션 안에서 동기로 발행되는지 본다. 파우치·가이드가 이 이벤트를 구독해 버전을
 * 올리므로 바뀌지 않았는데 발행하거나 바뀌었는데 빠뜨리면 안 된다.
 *
 * <p>"보이는 색"은 사용할 수 있는 칸의 HEX 다. 건마다 자기 트랜잭션으로 처리하므로 이 테스트는 트랜잭션으로 감싸지 않고, 테스트 전후에 표를 비운다.
 */
@Import({
  TestcontainersConfiguration.class,
  CatalogColorChangedEventTest.Recorder.class,
})
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql",
      "app.security.allowed-origins=http://localhost:3000",
      "catalog.color.min-quality.PRODUCT_PHOTO=0.8",
      "catalog.color.source-value-sites=OFFICIAL:etude.com"
    })
class CatalogColorChangedEventTest {

  private static final Path SAMPLE =
      Path.of("..", "shared", "catalog-import", "samples", "etude_option_image.json");
  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final Instant NOW = Instant.parse("2026-11-08T12:00:00Z");

  /** 이벤트를 받아 적어 두고, 원하면 예외를 던진다. */
  @TestConfiguration
  static class Recorder {
    final List<CatalogColorChanged> events = new CopyOnWriteArrayList<>();
    final List<Boolean> insideTransaction = new CopyOnWriteArrayList<>();
    volatile boolean failing;

    @EventListener
    void on(CatalogColorChanged event) {
      events.add(event);
      insideTransaction.add(TransactionSynchronizationManager.isActualTransactionActive());
      if (failing) {
        throw new IllegalStateException("listener boom");
      }
    }
  }

  @Autowired private CatalogImportService service;
  @Autowired private CatalogImportRunRepository runs;
  @Autowired private ProductRepository products;
  @Autowired private ProductTypeRepository types;
  @Autowired private JdbcTemplate jdbc;
  @Autowired private PlatformTransactionManager transactionManager;
  @Autowired private Recorder recorder;

  @BeforeEach
  void setUp() {
    clean();
    recorder.events.clear();
    recorder.insideTransaction.clear();
    recorder.failing = false;
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

  // --- 발행해야 하는 경우 ---

  @Test
  void newUsableColorsPublishOneEventWithTheChangedShadesInsideTheTransaction() throws Exception {
    UUID run = openRun("run-1");

    ItemResult result = service.importItem(run, item(n -> {}));

    assertThat(result.changedShadeIds()).hasSize(2);
    assertThat(recorder.events).hasSize(1);
    assertThat(recorder.events.get(0).shadeIds())
        .containsExactlyInAnyOrderElementsOf(result.changedShadeIds());
    assertThat(recorder.insideTransaction).containsExactly(true);
  }

  @Test
  void replacingAUsableColorWithADifferentValuePublishesForThatShadeOnly() throws Exception {
    service.importItem(openRun("run-1"), item(n -> {}));
    recorder.events.clear();

    ItemResult result =
        service.importItem(
            openRun("run-2"),
            item(
                n -> {
                  n.put("itemKey", "000009");
                  n.put("collectedAt", "2026-11-06T10:32:00+09:00");
                  color(n, 0).put("hex", "#101010");
                }));

    assertThat(result.changedShadeIds()).hasSize(1);
    assertThat(recorder.events).hasSize(1);
    assertThat(recorder.events.get(0).shadeIds())
        .containsExactlyElementsOf(result.changedShadeIds());
  }

  @Test
  void downgradingAUsableColorThatIsNoLongerAllowedPublishes() throws Exception {
    // 모델 추정 색은 기본 설정에서 쓸 수 없는 출처다. 사용 중으로 저장된 그 색을, 색을 못 찾은 수집이 내려야 한다
    ObjectNode sample = item(n -> {});
    String brand = sample.path("brand").asString();
    String name = sample.path("name").asString();
    String shadeName = sample.path("shades").get(0).path("name").asString();
    new TransactionTemplate(transactionManager)
        .executeWithoutResult(
            status -> {
              ProductType type = types.findById("MASCARA").orElseThrow();
              Product product = new Product(type, brand, name);
              product.recordSource(
                  "OFFICIAL:etude.com",
                  "example-curl-fix-mascara",
                  "https://www.etude.com/x",
                  Instant.parse("2026-11-01T00:00:00Z"));
              ProductShade shade = product.addShade(shadeName, 1, null);
              shade.changeSourceOptionId("01-black");
              ProductShadeColor slot = shade.addColor(1, null, NameSource.NONE);
              slot.assignColor(
                  ColorSource.LLM_ESTIMATE,
                  "#222222",
                  true,
                  ReviewStatus.AUTO_APPROVED,
                  Instant.parse("2026-11-01T00:00:00Z"));
              products.save(product);
            });

    ItemResult result =
        service.importItem(
            openRun("run-1"),
            item(
                n -> {
                  ObjectNode shade = (ObjectNode) n.path("shades").get(0);
                  shade.put("colorStatus", "NOT_FOUND");
                  ObjectNode slot = color(n, 0);
                  slot.remove("hex");
                  slot.remove("colorSource");
                  slot.remove("shadeLink");
                  slot.remove("colorQuality");
                }));

    assertThat(result.outcome()).isEqualTo(ImportItemOutcome.UPDATE);
    assertThat(result.reasons()).contains(ImportReason.COLOR_DOWNGRADED.name());
    Map<String, Object> slot =
        jdbc.queryForMap(
            "select c.color_hex, c.review_status from product_shade_colors c"
                + " join product_shades s on s.id = c.shade_id where s.source_option_id = '01-black'");
    assertThat(slot.get("color_hex")).isEqualTo("#222222");
    assertThat(slot.get("review_status")).isEqualTo("BELOW_THRESHOLD");
    // 내려간 호수(01)와, 이번 수집에서 새로 생겨 사용할 수 있는 색을 가진 호수(02)
    assertThat(result.changedShadeIds()).hasSize(2);
    assertThat(recorder.events).hasSize(1);
    assertThat(recorder.events.get(0).shadeIds()).hasSize(2);
  }

  // --- 발행하면 안 되는 경우 ---

  @Test
  void aColorThatIsStoredButNotUsableDoesNotChangeWhatTheServiceShows() throws Exception {
    ItemResult result =
        service.importItem(
            openRun("run-1"),
            item(
                n -> {
                  color(n, 0).put("colorQuality", 0.5);
                  color(n, 1).put("colorQuality", 0.5);
                }));

    assertThat(result.colorsApplied()).isEqualTo(2);
    assertThat(result.changedShadeIds()).isEmpty();
    assertThat(recorder.events).isEmpty();
    assertThat(jdbc.queryForList("select review_status from product_shade_colors", String.class))
        .containsOnly("BELOW_THRESHOLD");
  }

  @Test
  void collectingTheSameDataAgainPublishesNothing() throws Exception {
    service.importItem(openRun("run-1"), item(n -> {}));
    recorder.events.clear();

    service.importItem(openRun("run-2"), item(n -> {}));

    assertThat(recorder.events).isEmpty();
  }

  @Test
  void aResentItemDoesNotPublishAgain() throws Exception {
    UUID run = openRun("run-1");
    service.importItem(run, item(n -> {}));
    recorder.events.clear();

    ItemResult again = service.importItem(run, item(n -> {}));

    assertThat(again.duplicate()).isTrue();
    assertThat(recorder.events).isEmpty();
  }

  @Test
  void aStaleOrUnclassifiedItemPublishesNothing() throws Exception {
    service.importItem(openRun("run-1"), item(n -> {}));
    recorder.events.clear();

    service.importItem(
        openRun("run-2"),
        item(
            n -> {
              n.put("itemKey", "000009");
              n.put("collectedAt", "2026-11-01T10:32:00+09:00");
              color(n, 0).put("hex", "#101010");
            }));
    service.importItem(
        openRun("run-3"),
        item(
            n -> {
              n.put("typeHint", "NO_SUCH_TYPE");
              n.remove("categoryHint");
            }));

    assertThat(recorder.events).isEmpty();
  }

  // --- 구독자의 실패 ---

  @Test
  void aFailingSubscriberRollsTheWholeItemBackSoNoColorChangesWithoutItsNotice() throws Exception {
    recorder.failing = true;
    UUID run = openRun("run-1");

    ItemResult result = service.importItem(run, item(n -> {}));

    assertThat(result.outcome()).isEqualTo(ImportItemOutcome.FAILED);
    assertThat(result.recorded()).isTrue();
    assertThat(result.productId()).isNull();
    assertThat(recorder.events).hasSize(1);
    assertThat(jdbc.queryForObject("select count(*) from products", Integer.class)).isZero();
    assertThat(jdbc.queryForObject("select count(*) from product_shade_colors", Integer.class))
        .isZero();
    assertThat(
            jdbc.queryForObject(
                "select message from catalog_import_items where item_key = '000003'", String.class))
        .contains("listener boom");
  }
}
