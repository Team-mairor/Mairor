package com.mairor.backend.products.imports;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.products.entity.ImportItemOutcome;
import com.mairor.backend.products.entity.ImportRunStatus;
import com.mairor.backend.products.imports.CatalogImportRunService.RunView;
import com.mairor.backend.products.imports.CatalogImportRunService.StartCommand;
import com.mairor.backend.products.imports.CatalogImportService.ItemResult;
import com.mairor.backend.products.repository.CatalogImportRunRepository;
import com.mairor.backend.testsupport.MutableClock;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.JdbcTemplate;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/**
 * 적재 실행의 생명주기: 열기·이어 쓰기, 건 묶음, 하트비트, 끝내기, 끊긴 실행 정리. 시각은 가변 시계로 옮긴다. 건마다 자기 트랜잭션으로 처리하므로 이 테스트는
 * 트랜잭션으로 감싸지 않고 실제로 커밋시킨다. 그래서 테스트 전후에 표를 비운다.
 */
@Import({TestcontainersConfiguration.class, CatalogImportRunServiceTest.ClockConfig.class})
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql",
      "app.security.allowed-origins=http://localhost:3000",
      "catalog.import.heartbeat-timeout=10m",
      "catalog.color.min-quality.PRODUCT_PHOTO=0.8"
    })
class CatalogImportRunServiceTest {

  private static final Path SAMPLE =
      Path.of("..", "shared", "catalog-import", "samples", "etude_option_image.json");
  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final Instant START = Instant.parse("2026-11-08T12:00:00Z");

  /** 서비스가 쓰는 시계를 테스트가 움직인다. */
  @TestConfiguration
  static class ClockConfig {
    @Bean
    @Primary
    MutableClock catalogTestClock() {
      return new MutableClock(START);
    }
  }

  @Autowired private CatalogImportRunService service;
  @Autowired private CatalogImportRunRepository runs;
  @Autowired private JdbcTemplate jdbc;
  @Autowired private Clock clock;

  private MutableClock clock() {
    return (MutableClock) clock;
  }

  @BeforeEach
  void setUp() {
    clean();
    clock().set(START);
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

  private static StartCommand start(String runId) {
    return new StartCommand(runId, "OFFICIAL:etude.com", "0.1.0", START, "a.jsonl");
  }

  private static ObjectNode item(String itemKey) throws Exception {
    ObjectNode node = (ObjectNode) MAPPER.readTree(Files.readString(SAMPLE));
    node.put("itemKey", itemKey);
    return node;
  }

  private static ArrayNode array(ObjectNode... items) {
    ArrayNode array = MAPPER.createArrayNode();
    for (ObjectNode item : items) {
      array.add(item);
    }
    return array;
  }

  // --- 열기 ---

  @Test
  void aNewRunIsOpenedRunningAndOpeningItAgainResumesTheSameRun() {
    RunView first = service.start(start("run-1"));
    clock().advance(Duration.ofMinutes(3));

    RunView again = service.start(start("run-1"));

    assertThat(first.status()).isEqualTo(ImportRunStatus.RUNNING);
    assertThat(first.resumed()).isFalse();
    assertThat(again.resumed()).isTrue();
    assertThat(again.id()).isEqualTo(first.id());
    assertThat(again.lastHeartbeatAt()).isEqualTo(START.plus(Duration.ofMinutes(3)));
    assertThat(jdbc.queryForObject("select count(*) from catalog_import_runs", Integer.class))
        .isEqualTo(1);
  }

  @Test
  void aFinishedRunIdCannotBeOpenedAgain() {
    RunView run = service.start(start("run-1"));
    service.finish(run.id(), ImportRunStatus.COMPLETED);

    assertThatThrownBy(() -> service.start(start("run-1")))
        .isInstanceOf(CatalogImportRunClosedException.class);
  }

  @Test
  void openingTheSameRunIdAtTheSameTimeCreatesOneRun() throws Exception {
    int threads = 4;
    ExecutorService pool = Executors.newFixedThreadPool(threads);
    CountDownLatch go = new CountDownLatch(1);
    List<Future<RunView>> futures = new ArrayList<>();
    for (int i = 0; i < threads; i++) {
      futures.add(
          pool.submit(
              () -> {
                go.await();
                return service.start(start("run-1"));
              }));
    }
    go.countDown();
    List<RunView> views = new ArrayList<>();
    for (Future<RunView> future : futures) {
      views.add(future.get());
    }
    pool.shutdown();

    assertThat(views).filteredOn(v -> !v.resumed()).hasSize(1);
    assertThat(views).extracting(RunView::id).containsOnly(views.get(0).id());
    assertThat(jdbc.queryForObject("select count(*) from catalog_import_runs", Integer.class))
        .isEqualTo(1);
  }

  // --- 건 묶음 ---

  @Test
  void aBatchGivesOneResultPerItemAndRefreshesTheHeartbeat() throws Exception {
    RunView run = service.start(start("run-1"));
    clock().advance(Duration.ofMinutes(5));
    ObjectNode bad = item("000002");
    bad.remove("sourceProductId");

    List<ItemResult> results = service.importBatch(run.id(), array(item("000001"), bad));

    assertThat(results)
        .extracting(ItemResult::outcome)
        .containsExactly(ImportItemOutcome.NEW, ImportItemOutcome.INVALID);
    assertThat(results.get(1).message()).contains("sourceProductId");
    assertThat(service.get(run.id()).lastHeartbeatAt())
        .isEqualTo(START.plus(Duration.ofMinutes(5)));
  }

  @Test
  void resendingTheWholeBatchIsSafe() throws Exception {
    RunView run = service.start(start("run-1"));
    ArrayNode batch = array(item("000001"));
    service.importBatch(run.id(), batch);

    List<ItemResult> again = service.importBatch(run.id(), batch);

    assertThat(again).singleElement().satisfies(r -> assertThat(r.duplicate()).isTrue());
    assertThat(jdbc.queryForObject("select count(*) from catalog_import_items", Integer.class))
        .isEqualTo(1);
    assertThat(jdbc.queryForObject("select count(*) from products", Integer.class)).isEqualTo(1);
  }

  @Test
  void aBatchOutsideTheAllowedSizeOrShapeIsRejected() throws Exception {
    RunView run = service.start(start("run-1"));
    ArrayNode tooMany = MAPPER.createArrayNode();
    for (int i = 0; i < CatalogImportRunService.MAX_ITEMS + 1; i++) {
      tooMany.add(item(String.format("%06d", i)));
    }

    for (var bad : List.of(MAPPER.createObjectNode(), MAPPER.createArrayNode(), tooMany)) {
      assertThatThrownBy(() -> service.importBatch(run.id(), bad))
          .isInstanceOfSatisfying(
              BusinessException.class, e -> assertThat(e.code()).isEqualTo("VALIDATION_FAILED"));
    }
    assertThatThrownBy(() -> service.importBatch(run.id(), null))
        .isInstanceOf(BusinessException.class);
  }

  // --- 끝내기 ---

  @Test
  void finishingRecordsTheTimeAndIsRepeatableWithTheSameStatus() {
    RunView run = service.start(start("run-1"));
    clock().advance(Duration.ofMinutes(1));

    RunView done = service.finish(run.id(), ImportRunStatus.COMPLETED);
    RunView again = service.finish(run.id(), ImportRunStatus.COMPLETED);

    assertThat(done.status()).isEqualTo(ImportRunStatus.COMPLETED);
    assertThat(done.finishedAt()).isEqualTo(START.plus(Duration.ofMinutes(1)));
    assertThat(again.status()).isEqualTo(ImportRunStatus.COMPLETED);
    assertThat(again.finishedAt()).isEqualTo(done.finishedAt());
  }

  @Test
  void aRunFinishedOneWayCannotBeFinishedAnotherWay() {
    RunView run = service.start(start("run-1"));
    service.finish(run.id(), ImportRunStatus.FAILED);

    assertThatThrownBy(() -> service.finish(run.id(), ImportRunStatus.COMPLETED))
        .isInstanceOf(CatalogImportRunClosedException.class);
  }

  @Test
  void theCollectorCannotSetTheStatesOnlyTheServerDecides() {
    RunView run = service.start(start("run-1"));

    assertThatThrownBy(() -> service.finish(run.id(), ImportRunStatus.ABANDONED))
        .isInstanceOf(IllegalArgumentException.class);
    assertThatThrownBy(() -> service.finish(run.id(), ImportRunStatus.RUNNING))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void anUnknownRunIsNotFoundEverywhere() throws Exception {
    UUID missing = UUID.randomUUID();

    assertThatThrownBy(() -> service.heartbeat(missing))
        .isInstanceOf(CatalogImportRunNotFoundException.class);
    assertThatThrownBy(() -> service.importBatch(missing, array(item("000001"))))
        .isInstanceOf(CatalogImportRunNotFoundException.class);
    assertThatThrownBy(() -> service.finish(missing, ImportRunStatus.COMPLETED))
        .isInstanceOf(CatalogImportRunNotFoundException.class);
  }

  // --- 하트비트와 끊긴 실행 ---

  @Test
  void aRunWithoutHeartbeatsIsAbandonedAndOnesWithRecentHeartbeatsAreKept() {
    RunView stale = service.start(start("stale"));
    RunView fresh = service.start(start("fresh"));
    RunView finished = service.start(start("finished"));
    service.finish(finished.id(), ImportRunStatus.COMPLETED);
    clock().advance(Duration.ofMinutes(9));
    service.heartbeat(fresh.id());
    clock().advance(Duration.ofMinutes(2));

    int count = service.abandonStale();

    assertThat(count).isEqualTo(1);
    assertThat(service.get(stale.id()).status()).isEqualTo(ImportRunStatus.ABANDONED);
    assertThat(service.get(stale.id()).finishedAt()).isEqualTo(clock().instant());
    assertThat(service.get(fresh.id()).status()).isEqualTo(ImportRunStatus.RUNNING);
    assertThat(service.get(finished.id()).status()).isEqualTo(ImportRunStatus.COMPLETED);
    assertThat(service.abandonStale()).isZero();
  }

  @Test
  void anAbandonedRunRefusesItemsHeartbeatsAndFinishing() throws Exception {
    RunView run = service.start(start("run-1"));
    clock().advance(Duration.ofMinutes(11));
    service.abandonStale();

    assertThatThrownBy(() -> service.importBatch(run.id(), array(item("000001"))))
        .isInstanceOf(CatalogImportRunClosedException.class);
    assertThatThrownBy(() -> service.heartbeat(run.id()))
        .isInstanceOf(CatalogImportRunClosedException.class);
    assertThatThrownBy(() -> service.finish(run.id(), ImportRunStatus.COMPLETED))
        .isInstanceOf(CatalogImportRunClosedException.class);
    assertThat(jdbc.queryForObject("select count(*) from catalog_import_items", Integer.class))
        .isZero();
  }

  @Test
  void aHeartbeatCannotReviveARunTheCleanupAlreadyEnded() {
    RunView run = service.start(start("run-1"));
    clock().advance(Duration.ofMinutes(11));
    service.abandonStale();

    assertThat(runs.touchIfRunning(run.id(), clock().instant())).isZero();
    assertThat(service.get(run.id()).status()).isEqualTo(ImportRunStatus.ABANDONED);
  }

  @Test
  void sendingItemsKeepsALongRunAliveBeyondTheTimeout() throws Exception {
    RunView run = service.start(start("run-1"));
    clock().advance(Duration.ofMinutes(9));
    service.importBatch(run.id(), array(item("000001")));
    clock().advance(Duration.ofMinutes(9));

    assertThat(service.abandonStale()).isZero();
    assertThat(service.get(run.id()).status()).isEqualTo(ImportRunStatus.RUNNING);
  }
}
