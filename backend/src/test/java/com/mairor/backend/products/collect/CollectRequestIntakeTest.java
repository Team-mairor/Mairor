package com.mairor.backend.products.collect;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.users.support.AuthenticatedUser;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
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
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

/** 직접 입력 등록 뒤 수집 요청 접수(S15P31A306-517)를 등록 API 부터 PostgreSQL 까지 확인한다. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql,classpath:db/schema/executions.sql",
      "app.security.allowed-origins=http://localhost:3000",
      "catalog.collect.types=CLT_TINT",
      "catalog.collect.daily-limit-per-user=3"
    })
@AutoConfigureMockMvc
class CollectRequestIntakeTest {

  private static final String PATH = "/v1/users/me/pouch-items";
  private static final String CATEGORY = "CLT_LIP";
  private static final String TYPE = "CLT_TINT";
  private static final String OTHER_TYPE = "CLT_BALM";

  @Autowired private MockMvc mockMvc;
  @Autowired private JdbcTemplate jdbc;

  private final List<UUID> users = new ArrayList<>();
  private final List<UUID> products = new ArrayList<>();
  private String brand;

  @BeforeEach
  void setUp() {
    jdbc.update(
        "insert into product_categories values (?, '수집 시험', true, true, 90)"
            + " on conflict do nothing",
        CATEGORY);
    jdbc.update(
        "insert into product_types values (?, ?, '수집 틴트', 1), (?, ?, '수집 밤', 2)"
            + " on conflict do nothing",
        TYPE,
        CATEGORY,
        OTHER_TYPE,
        CATEGORY);
    brand = "브랜드" + UUID.randomUUID().toString().substring(0, 8);
  }

  @AfterEach
  void cleanUp() {
    jdbc.update(
        "delete from catalog_collect_requests where brand = ? or request_key like 'URL|https://"
            + "shop.example/%'",
        brand);
    for (UUID user : users) {
      jdbc.update("delete from pouch_items where user_id = ?", user);
      jdbc.update("delete from users where id = ?", user);
    }
    for (UUID product : products) {
      jdbc.update("delete from product_shades where product_id = ?", product);
      jdbc.update("delete from products where id = ?", product);
    }
  }

  @Test
  void aManualItemOfACollectedTypeQueuesARequestWithTheItemAsRequester() throws Exception {
    UUID user = member();

    register(user, TYPE, "쥬시 래스팅 틴트", "01 니어");

    Map<String, Object> request = onlyRequest();
    assertThat(request)
        .containsEntry("status", "QUEUED")
        .containsEntry("trigger", "USER")
        .containsEntry("name", "쥬시 래스팅 틴트")
        .containsEntry("shade_name", "01 니어")
        .containsEntry("type_code", TYPE);
    assertThat((String) request.get("request_key")).endsWith("|쥬시래스팅틴트");
    Map<String, Object> requester =
        jdbc.queryForMap(
            "select u.*, p.updated_at as item_updated from catalog_collect_request_users u"
                + " join pouch_items p on p.id = u.pouch_item_id where u.request_id = ?",
            request.get("id"));
    assertThat(requester.get("user_id")).isEqualTo(user);
    assertThat(requester.get("pouch_item_updated_at")).isEqualTo(requester.get("item_updated"));
  }

  @Test
  void theSameProductWithOtherSpacingJoinsTheOpenRequest() throws Exception {
    register(member(), TYPE, "쥬시 래스팅 틴트", null);
    register(member(), TYPE, "쥬시래스팅 틴트", null);

    Map<String, Object> request = onlyRequest();
    assertThat(
            jdbc.queryForObject(
                "select count(*) from catalog_collect_request_users where request_id = ?",
                Long.class,
                request.get("id")))
        .isEqualTo(2);
  }

  @Test
  void otherTypesAndCatalogRegistrationsMakeNoRequest() throws Exception {
    UUID user = member();
    register(user, OTHER_TYPE, "립밤", null);
    UUID product = product("카탈로그 틴트", null);
    UUID shade = UUID.randomUUID();
    jdbc.update(
        "insert into product_shades (id, product_id, name, name_normalized, sort_order,"
            + " created_at, updated_at) values (?, ?, '01', '01', 1, now(), now())",
        shade,
        product);
    String catalog =
        """
        {"registrationMode":"CATALOG","type":"%s","productId":"%s","shadeId":"%s"}
        """
            .formatted(TYPE, product, shade);
    mockMvc.perform(write(user, catalog)).andExpect(status().isCreated());

    assertThat(requestCount()).isZero();
  }

  @Test
  void aProductAlreadyInTheCatalogEndsResolvedWithoutCollecting() throws Exception {
    product("쥬시 래스팅 틴트", null);

    register(member(), TYPE, "쥬시래스팅틴트", null);

    assertThat(onlyRequest())
        .containsEntry("status", "RESOLVED")
        .satisfies(r -> assertThat(r.get("finished_at")).isNotNull());
  }

  @Test
  void aMissingShadeOfAKnownProductIsCollectedAgainFromItsPage() throws Exception {
    UUID product = product("쥬시 래스팅 틴트", "https://shop.example/product/1");
    jdbc.update(
        "insert into product_shades (id, product_id, name, name_normalized, sort_order,"
            + " created_at, updated_at) values (gen_random_uuid(), ?, '01 니어', '01 니어', 1,"
            + " now(), now())",
        product);

    register(member(), TYPE, "쥬시 래스팅 틴트", "02 레드");

    assertThat(onlyRequest())
        .containsEntry("status", "QUEUED")
        .containsEntry("name", null)
        .containsEntry("product_url", "https://shop.example/product/1")
        .containsEntry("request_key", "URL|https://shop.example/product/1");
  }

  @Test
  void twoProductsThatDifferOnlyInSpacingEndUnresolved() throws Exception {
    product("쥬시 래스팅틴트", null);
    product("쥬시래스팅 틴트", null);

    register(member(), TYPE, "쥬시래스팅틴트", null);

    assertThat(onlyRequest())
        .containsEntry("status", "UNRESOLVED")
        .containsEntry("reason", "MULTIPLE_CANDIDATES");
  }

  @Test
  void aProductThatWasJustNotFoundIsNotRequestedAgain() throws Exception {
    register(member(), TYPE, "없는 틴트", null);
    Map<String, Object> first = onlyRequest();
    jdbc.update(
        "update catalog_collect_requests set status = 'NOT_FOUND', reason = 'SEARCH_EMPTY',"
            + " finished_at = ? where id = ?",
        Timestamp.from(Instant.now()),
        first.get("id"));

    register(member(), TYPE, "없는 틴트", null);

    assertThat(requestCount()).isEqualTo(1);
  }

  @Test
  void aMemberStopsRequestingAtTheDailyLimit() throws Exception {
    UUID user = member();
    for (int i = 1; i <= 4; i++) {
      register(user, TYPE, "틴트 " + i, null);
    }

    assertThat(requestCount()).isEqualTo(3);
  }

  private void register(UUID user, String type, String name, String shadeName) throws Exception {
    String json =
        """
        {"registrationMode":"MANUAL","category":"%s","type":"%s","brand":"%s","name":"%s","shadeName":%s}
        """
            .formatted(
                CATEGORY, type, brand, name, shadeName == null ? "null" : "\"" + shadeName + "\"");
    mockMvc.perform(write(user, json)).andExpect(status().isCreated());
  }

  private Map<String, Object> onlyRequest() {
    List<Map<String, Object>> rows =
        jdbc.queryForList("select * from catalog_collect_requests where brand = ?", brand);
    assertThat(rows).hasSize(1);
    return rows.getFirst();
  }

  private long requestCount() {
    return jdbc.queryForObject(
        "select count(*) from catalog_collect_requests where brand = ?", Long.class, brand);
  }

  private UUID member() {
    UUID id = UUID.randomUUID();
    users.add(id);
    jdbc.update(
        "insert into users (id, email, provider, created_at, updated_at)"
            + " values (?, ?, 'LOCAL', now(), now())",
        id,
        id + "@example.com");
    return id;
  }

  private UUID product(String name, String sourceUrl) {
    UUID id = UUID.randomUUID();
    products.add(id);
    jdbc.update(
        "insert into products (id, brand, name, brand_normalized, name_normalized, category_code,"
            + " type_code, source, source_product_id, source_url, created_at, updated_at)"
            + " values (?, ?, ?, lower(?), lower(?), ?, ?, ?, ?, ?, now(), now())",
        id,
        brand,
        name,
        brand,
        name,
        CATEGORY,
        TYPE,
        sourceUrl == null ? null : "OFFICIAL:shop.example",
        sourceUrl == null ? null : id.toString(),
        sourceUrl);
    return id;
  }

  private org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder write(
      UUID user, String json) {
    return post(PATH)
        .with(asMember(user))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content(json);
  }

  private static RequestPostProcessor asMember(UUID id) {
    return authentication(
        UsernamePasswordAuthenticationToken.authenticated(
            new AuthenticatedUser(id, "member@example.com"),
            null,
            List.of(new SimpleGrantedAuthority("ROLE_USER"))));
  }
}
