package com.mairor.backend.products.entity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.products.repository.CatalogCollectRequestRepository;
import com.mairor.backend.products.repository.CatalogCollectRequestUserRepository;
import jakarta.persistence.EntityManager;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
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
 * 수집 요청 테이블({@code catalog_collect_requests}·{@code catalog_collect_request_users})의 SQL 규칙과 엔티티
 * 저장·읽기를 확인한다. 진행 중 요청이 제품마다 하나뿐인 부분 유니크처럼 JPA 로 표현할 수 없는 규칙은 SQL 로 넣어 본다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql,classpath:db/schema/executions.sql",
      "app.security.allowed-origins=http://localhost:3000"
    })
@Transactional
class CatalogCollectSqlTest {

  private static final Instant NOW = Instant.parse("2026-11-12T12:00:00Z");
  private static final String KEY = "LIP|LIP_TINT|롬앤|쥬시래스팅틴트";

  private static final String INSERT_REQUEST =
      "insert into catalog_collect_requests (id, trigger, request_key, brand, name, product_url,"
          + " status, sent_at, finished_at, created_at, updated_at)"
          + " values (gen_random_uuid(), ?, ?, '롬앤', ?, ?, ?, ?::timestamptz, ?::timestamptz,"
          + " now(), now())";

  @Autowired private JdbcTemplate jdbc;
  @Autowired private EntityManager em;
  @Autowired private CatalogCollectRequestRepository requests;
  @Autowired private CatalogCollectRequestUserRepository requestUsers;

  private UUID userId;

  @BeforeEach
  void setUp() {
    userId = UUID.randomUUID();
    jdbc.update(
        "insert into users (id, email, provider, created_at, updated_at)"
            + " values (?, ?, 'LOCAL', now(), now())",
        userId,
        "collect-" + userId + "@example.com");
    ProductCategory lip = new ProductCategory("LIP", "립", true, true, 5);
    em.persist(lip);
    em.persist(new ProductType("LIP_TINT", lip, "립틴트", 3));
    em.flush();
  }

  @Test
  void constraintsAndIndexesUseTheNamesTheCodeDependsOn() {
    assertThat(constraints("catalog_collect_requests"))
        .contains(
            "catalog_collect_requests_pkey",
            CatalogCollectRequest.IMPORT_RUN_FK,
            CatalogCollectRequest.TRIGGER_CHECK,
            CatalogCollectRequest.STATUS_CHECK,
            CatalogCollectRequest.TARGET_CHECK,
            CatalogCollectRequest.FINISHED_CHECK,
            CatalogCollectRequest.SENT_CHECK,
            CatalogCollectRequest.ATTEMPTS_CHECK);
    assertThat(constraints("catalog_collect_request_users"))
        .contains(
            "catalog_collect_request_users_pkey",
            CatalogCollectRequestUser.REQUEST_FK,
            CatalogCollectRequestUser.USER_FK,
            CatalogCollectRequestUser.POUCH_ITEM_FK,
            CatalogCollectRequestUser.REQUEST_ITEM_UNIQUE);
    assertThat(indexColumns("catalog_collect_requests"))
        .containsEntry(CatalogCollectRequest.OPEN_KEY_UNIQUE, List.of("request_key"))
        .containsEntry(
            CatalogCollectRequest.KEY_FINISHED_INDEX, List.of("request_key", "finished_at"))
        .containsEntry(CatalogCollectRequest.STATUS_UPDATED_INDEX, List.of("status", "updated_at"));
    assertThat(indexColumns("catalog_collect_request_users"))
        .containsEntry(
            CatalogCollectRequestUser.USER_CREATED_INDEX, List.of("user_id", "created_at"))
        .containsEntry(CatalogCollectRequestUser.POUCH_ITEM_INDEX, List.of("pouch_item_id"));
  }

  @Test
  void onlyOneOpenRequestPerKeyButFinishedOnesCanRepeat() {
    update(INSERT_REQUEST, "USER", KEY, "쥬시 틴트", null, "QUEUED", null, null);
    update(INSERT_REQUEST, "USER", KEY, "쥬시 틴트", null, "NOT_FOUND", null, NOW.toString());
    update(INSERT_REQUEST, "USER", KEY, "쥬시 틴트", null, "FAILED", null, NOW.toString());

    assertThatThrownBy(
            () -> update(INSERT_REQUEST, "USER", KEY, "쥬시 틴트", null, "SENT", NOW.toString(), null))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(CatalogCollectRequest.OPEN_KEY_UNIQUE);
  }

  @Test
  void aRequestNamesExactlyOneTarget() {
    assertThatThrownBy(
            () ->
                update(
                    INSERT_REQUEST,
                    "USER",
                    KEY,
                    "쥬시",
                    "https://a.example/p/1",
                    "QUEUED",
                    null,
                    null))
        .hasMessageContaining(CatalogCollectRequest.TARGET_CHECK);
    assertThatThrownBy(() -> update(INSERT_REQUEST, "USER", KEY, null, null, "QUEUED", null, null))
        .hasMessageContaining(CatalogCollectRequest.TARGET_CHECK);
  }

  @Test
  void statusFinishedAtAndSentAtStayConsistent() {
    assertThatThrownBy(
            () -> update(INSERT_REQUEST, "USER", KEY, "쥬시", null, "RESOLVED", null, null))
        .hasMessageContaining(CatalogCollectRequest.FINISHED_CHECK);
    assertThatThrownBy(
            () -> update(INSERT_REQUEST, "USER", KEY, "쥬시", null, "QUEUED", null, NOW.toString()))
        .hasMessageContaining(CatalogCollectRequest.FINISHED_CHECK);
    assertThatThrownBy(() -> update(INSERT_REQUEST, "USER", KEY, "쥬시", null, "SENT", null, null))
        .hasMessageContaining(CatalogCollectRequest.SENT_CHECK);
    assertThatThrownBy(() -> update(INSERT_REQUEST, "BOT", KEY, "쥬시", null, "QUEUED", null, null))
        .hasMessageContaining(CatalogCollectRequest.TRIGGER_CHECK);
    assertThatThrownBy(
            () -> update(INSERT_REQUEST, "USER", KEY, "쥬시", null, "PAUSED", null, NOW.toString()))
        .hasMessageContaining(CatalogCollectRequest.STATUS_CHECK);
  }

  @Test
  void theEntityRoundTripsAndKeepsItsOwnId() {
    CatalogCollectRequest request =
        new CatalogCollectRequest(
            CollectTrigger.USER, KEY, "LIP", "LIP_TINT", "롬앤", "쥬시 틴트", null, "01 니어");
    UUID jobId = request.getId();
    requests.save(request);
    request.markSent(NOW);
    em.flush();
    em.clear();

    CatalogCollectRequest found = requests.findById(jobId).orElseThrow();
    assertThat(found.getStatus()).isEqualTo(CollectRequestStatus.SENT);
    assertThat(found.getSendAttempts()).isEqualTo(1);
    assertThat(found.getShadeName()).isEqualTo("01 니어");

    found.recordResult("SEARCH_EMPTY", null, null);
    found.finish(CollectRequestStatus.NOT_FOUND, "SEARCH_EMPTY", NOW);
    em.flush();
    em.clear();
    assertThat(requests.findById(jobId).orElseThrow().getFinishedAt()).isEqualTo(NOW);
  }

  @Test
  void requestersFollowTheirRequestAndLoseDeletedPouchItems() {
    CatalogCollectRequest request =
        requests.save(
            new CatalogCollectRequest(
                CollectTrigger.USER, KEY, "LIP", "LIP_TINT", "롬앤", "쥬시 틴트", null, null));
    UUID itemId = UUID.randomUUID();
    jdbc.update(
        "insert into pouch_items (id, user_id, registration_mode, category_code, type_code, brand,"
            + " name, brand_normalized, name_normalized, shade_name_normalized, created_at,"
            + " updated_at) values (?, ?, 'MANUAL', 'LIP', 'LIP_TINT', '롬앤', '쥬시 틴트', '롬앤',"
            + " '쥬시 틴트', '', now(), now())",
        itemId,
        userId);
    requestUsers.save(new CatalogCollectRequestUser(request.getId(), userId, itemId, NOW));
    em.flush();

    jdbc.update("delete from pouch_items where id = ?", itemId);
    em.clear();
    assertThat(requestUsers.findByRequestId(request.getId()))
        .singleElement()
        .satisfies(row -> assertThat(row.getPouchItemId()).isNull());

    jdbc.update("delete from catalog_collect_requests where id = ?", request.getId());
    assertThat(requestUsers.findByRequestId(request.getId())).isEmpty();
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
                Collectors.mapping(r -> (String) r.get("column_name"), Collectors.toList())));
  }
}
