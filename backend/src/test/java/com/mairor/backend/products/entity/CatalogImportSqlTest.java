package com.mairor.backend.products.entity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.products.repository.CatalogImportItemRepository;
import com.mairor.backend.products.repository.CatalogImportRunRepository;
import com.mairor.backend.products.repository.ProductRepository;
import com.mairor.backend.products.repository.ProductShadeColorRepository;
import jakarta.persistence.EntityManager;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

/**
 * 적재 실행 테이블({@code catalog_import_runs}·{@code catalog_import_items})과 색 칸의 출처 연결 컬럼을 확인한다. 엔티티를
 * 거치지 않고 SQL 로 넣은 데이터도 DB 가 막아야 하는 규칙과, 엔티티로 저장하고 읽는 경로를 함께 본다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql",
      "app.security.allowed-origins=http://localhost:3000"
    })
@Transactional
class CatalogImportSqlTest {

  private static final Instant NOW = Instant.parse("2026-11-08T12:00:00Z");

  private static final String INSERT_RUN =
      "insert into catalog_import_runs (id, run_id, status, last_heartbeat_at, finished_at,"
          + " created_at, updated_at) values (?::uuid, ?, ?, now(), ?::timestamptz, now(), now())";
  private static final String INSERT_ITEM =
      "insert into catalog_import_items (id, run_id, item_key, outcome, partial, reasons,"
          + " colors_applied, created_at, updated_at)"
          + " values (gen_random_uuid(), ?::uuid, ?, ?, false, '', ?, now(), now())";

  private static final String RUN_ID = "00000000-0000-4000-8000-0000000000a1";
  private static final String OTHER_RUN_ID = "00000000-0000-4000-8000-0000000000a2";

  @Autowired private JdbcTemplate jdbc;
  @Autowired private EntityManager em;
  @Autowired private CatalogImportRunRepository runs;
  @Autowired private CatalogImportItemRepository items;
  @Autowired private ProductRepository products;
  @Autowired private ProductShadeColorRepository colors;

  private ProductType tint;

  @BeforeEach
  void setUp() {
    update(INSERT_RUN, RUN_ID, "run-1", "RUNNING", null);
    ProductCategory lip = new ProductCategory("LIP", "립", true, true, 5);
    em.persist(lip);
    tint = new ProductType("LIP_TINT", lip, "립틴트", 3);
    em.persist(tint);
    em.flush();
  }

  // --- 제약 이름 ---

  @Test
  void constraintsAndIndexesUseTheNamesTheCodeDependsOn() {
    assertThat(constraints("catalog_import_runs"))
        .contains(
            "catalog_import_runs_pkey",
            CatalogImportRun.RUN_ID_UNIQUE,
            CatalogImportRun.STATUS_CHECK,
            CatalogImportRun.FINISHED_CHECK);
    assertThat(constraints("catalog_import_items"))
        .contains(
            "catalog_import_items_pkey",
            CatalogImportItem.RUN_FK,
            CatalogImportItem.PRODUCT_FK,
            CatalogImportItem.RUN_ITEM_UNIQUE,
            CatalogImportItem.OUTCOME_CHECK,
            CatalogImportItem.COLORS_CHECK);
    assertThat(constraints("product_shade_colors"))
        .contains(ProductShadeColor.SOURCE_ITEM_FK, ProductShadeColor.SOURCE_PAIR_CHECK);
    assertThat(indexColumns("catalog_import_runs"))
        .containsEntry(
            CatalogImportRun.STATUS_HEARTBEAT_INDEX, List.of("status", "last_heartbeat_at"));
    assertThat(indexColumns("catalog_import_items"))
        .containsEntry(CatalogImportItem.RUN_OUTCOME_INDEX, List.of("run_id", "outcome"))
        .containsEntry(CatalogImportItem.PRODUCT_INDEX, List.of("product_id"));
    assertThat(indexColumns("product_shade_colors"))
        .containsEntry(ProductShadeColor.SOURCE_ITEM_INDEX, List.of("source_item_id"));
  }

  // --- 실행 ---

  @Test
  void aRunIdCanOnlyBeUsedOnce() {
    assertThatThrownBy(() -> update(INSERT_RUN, OTHER_RUN_ID, "run-1", "RUNNING", null))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(CatalogImportRun.RUN_ID_UNIQUE);
  }

  @Test
  void runStatusMustBeOneOfTheKnownValues() {
    // 진행 중이 아닌 값으로 finished_at 을 채워 두어야 상태 검사까지 간다
    assertThatThrownBy(() -> update(INSERT_RUN, OTHER_RUN_ID, "run-2", "PAUSED", NOW.toString()))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(CatalogImportRun.STATUS_CHECK);
  }

  @Test
  void aRunIsFinishedExactlyWhenItIsNotRunning() {
    // 끝났는데 finished_at 이 없다
    assertThatThrownBy(() -> update(INSERT_RUN, OTHER_RUN_ID, "run-2", "COMPLETED", null))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(CatalogImportRun.FINISHED_CHECK);
    // 진행 중인데 finished_at 이 있다
    assertThatThrownBy(() -> update(INSERT_RUN, OTHER_RUN_ID, "run-3", "RUNNING", NOW.toString()))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(CatalogImportRun.FINISHED_CHECK);
    update(INSERT_RUN, OTHER_RUN_ID, "run-4", "ABANDONED", NOW.toString());
  }

  // --- 건 ---

  @Test
  void anItemKeyCanOnlyBeUsedOncePerRun() {
    update(INSERT_ITEM, RUN_ID, "000001", "NEW", 2);
    assertThatThrownBy(() -> update(INSERT_ITEM, RUN_ID, "000001", "NEW", 0))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(CatalogImportItem.RUN_ITEM_UNIQUE);
    update(INSERT_RUN, OTHER_RUN_ID, "run-2", "RUNNING", null);
    update(INSERT_ITEM, OTHER_RUN_ID, "000001", "NEW", 0);
  }

  @Test
  void itemOutcomeAndColorCountAreChecked() {
    assertThatThrownBy(() -> update(INSERT_ITEM, RUN_ID, "000002", "DONE", 0))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(CatalogImportItem.OUTCOME_CHECK);
    assertThatThrownBy(() -> update(INSERT_ITEM, RUN_ID, "000003", "NEW", -1))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(CatalogImportItem.COLORS_CHECK);
    for (ImportItemOutcome outcome : ImportItemOutcome.values()) {
      update(INSERT_ITEM, RUN_ID, "k-" + outcome, outcome.name(), 0);
    }
  }

  @Test
  void anItemMustBelongToAnExistingRun() {
    assertThatThrownBy(
            () -> update(INSERT_ITEM, "00000000-0000-4000-8000-0000000000ff", "000001", "NEW", 0))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(CatalogImportItem.RUN_FK);
  }

  // --- 색 칸의 출처 연결 ---

  @Test
  void slotSourceItemAndEvidenceKeyComeTogether() {
    String shadeId = insertShade().toString();
    update(INSERT_ITEM, RUN_ID, "000001", "NEW", 1);
    String itemId =
        jdbc.queryForObject(
            "select id::text from catalog_import_items where item_key = '000001'", String.class);
    String insertSlot =
        "insert into product_shade_colors (id, shade_id, sort_order, name_source, source_item_id,"
            + " source_evidence_key, created_at, updated_at)"
            + " values (gen_random_uuid(), ?::uuid, ?, 'NONE', ?::uuid, ?, now(), now())";

    assertThatThrownBy(() -> update(insertSlot, shadeId, 1, itemId, null))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(ProductShadeColor.SOURCE_PAIR_CHECK);
    assertThatThrownBy(() -> update(insertSlot, shadeId, 1, null, "p/o/1"))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(ProductShadeColor.SOURCE_PAIR_CHECK);
    assertThatThrownBy(
            () -> update(insertSlot, shadeId, 1, "00000000-0000-4000-8000-0000000000ff", "p/o/1"))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(ProductShadeColor.SOURCE_ITEM_FK);
    update(insertSlot, shadeId, 1, itemId, "p/o/1");
    update(insertSlot, shadeId, 2, null, null);
  }

  // --- 엔티티 경로 ---

  @Test
  void entitiesRoundTripAndLinkASlotToItsItem() {
    CatalogImportRun run =
        runs.saveAndFlush(
            new CatalogImportRun(
                "run-entity",
                "OFFICIAL:etude.com",
                "0.1.0",
                "20261108-120000-etude.jsonl",
                NOW,
                NOW));
    CatalogImportItem item = new CatalogImportItem(run, "000001", "OFFICIAL:etude.com", "47508");
    item.recordResult(
        ImportItemOutcome.NEW, false, List.of("B_REASON", "A_REASON", "A_REASON"), null, 2, null);
    items.saveAndFlush(item);

    Product product = new Product(tint, "ETUDE", "Tint");
    ProductShade shade = product.addShade("01 로즈", 1, null);
    ProductShadeColor slot = shade.addColor(1, null, NameSource.NONE);
    slot.linkSource(item, "47508/01 로즈/1");
    products.saveAndFlush(product);
    em.clear();

    ProductShadeColor read = colors.findById(slot.getId()).orElseThrow();
    assertThat(read.getSourceItem().getItemKey()).isEqualTo("000001");
    assertThat(read.getSourceItem().getRun().getResultFile())
        .isEqualTo("20261108-120000-etude.jsonl");
    assertThat(read.getSourceEvidenceKey()).isEqualTo("47508/01 로즈/1");
    assertThat(runs.findByRunId("run-entity")).isPresent();
    assertThat(items.findByRunAndItemKey(run, "000001").orElseThrow().getReasonCodes())
        .containsExactly("A_REASON", "B_REASON");
    assertThat(run.getStatus()).isEqualTo(ImportRunStatus.RUNNING);
    assertThat(run.getFinishedAt()).isNull();
  }

  @Test
  void aFinishedRunKeepsItsFinishTimeThroughTheDatabase() {
    CatalogImportRun run = new CatalogImportRun("run-finish", null, null, null, null, NOW);
    run.complete(NOW.plusSeconds(60));
    runs.saveAndFlush(run);

    CatalogImportRun read = runs.findByRunId("run-finish").orElseThrow();
    assertThat(read.getStatus()).isEqualTo(ImportRunStatus.COMPLETED);
    assertThat(read.getFinishedAt()).isEqualTo(NOW.plusSeconds(60));
  }

  @Test
  void savingAnItemWithoutARecordedResultIsRefusedBeforeTheDatabaseSeesIt() {
    CatalogImportRun run =
        runs.saveAndFlush(new CatalogImportRun("run-x", null, null, null, null, NOW));
    CatalogImportItem item = new CatalogImportItem(run, "000001", null, null);

    assertThatThrownBy(() -> items.saveAndFlush(item))
        .hasRootCauseInstanceOf(IllegalStateException.class);
  }

  /** 호수 하나를 가진 제품을 저장하고 호수 id 를 돌려준다. */
  private java.util.UUID insertShade() {
    Product product = new Product(tint, "ETUDE", "Tint");
    ProductShade shade = product.addShade("01 로즈", 1, null);
    products.saveAndFlush(product);
    return shade.getId();
  }

  private void update(String sql, Object... args) {
    jdbc.execute("savepoint attempt");
    try {
      jdbc.update(sql, args);
    } catch (RuntimeException e) {
      jdbc.execute("rollback to savepoint attempt");
      throw e;
    }
    jdbc.execute("release savepoint attempt");
  }

  private List<String> constraints(String table) {
    return jdbc.queryForList(
        "select conname from pg_constraint where conrelid = ?::regclass", String.class, table);
  }

  private Map<String, List<String>> indexColumns(String table) {
    return jdbc
        .queryForList(
            "select i.relname as index_name, a.attname as column_name, k.ord"
                + " from pg_index x"
                + " join pg_class i on i.oid = x.indexrelid"
                + " join pg_class t on t.oid = x.indrelid"
                + " cross join lateral unnest(x.indkey) with ordinality as k(attnum, ord)"
                + " join pg_attribute a on a.attrelid = t.oid and a.attnum = k.attnum"
                + " where t.relname = ? order by i.relname, k.ord",
            table)
        .stream()
        .collect(
            Collectors.groupingBy(
                r -> (String) r.get("index_name"),
                java.util.LinkedHashMap::new,
                Collectors.mapping(r -> (String) r.get("column_name"), Collectors.toList())));
  }
}
