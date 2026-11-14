package com.mairor.backend.products.collect;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.common.security.InternalTokenFilter;
import com.mairor.backend.users.support.AuthenticatedUser;
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

/** 해결된 수집 요청의 직접 입력 파우치 항목을 카탈로그에 자동 연결하기(S15P31A306-517). 등록부터 결과 콜백까지 실제 경로로 본다. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql,classpath:db/schema/executions.sql",
      "app.security.allowed-origins=http://localhost:3000",
      "app.internal.token=" + CollectPouchLinkTest.TOKEN,
      "catalog.collect.types=CLK_TINT"
    })
@AutoConfigureMockMvc
class CollectPouchLinkTest {

  static final String TOKEN = "collect-link-token";
  private static final String CATEGORY = "CLK_LIP";
  private static final String TYPE = "CLK_TINT";

  @Autowired private MockMvc mockMvc;
  @Autowired private JdbcTemplate jdbc;

  private UUID user;
  private String brand;

  @BeforeEach
  void setUp() {
    jdbc.update(
        "insert into product_categories values (?, '연결 시험', true, true, 93) on conflict do nothing",
        CATEGORY);
    jdbc.update(
        "insert into product_types values (?, ?, '연결 틴트', 1) on conflict do nothing",
        TYPE,
        CATEGORY);
    user = member();
    brand = "연결" + UUID.randomUUID().toString().substring(0, 8);
  }

  @AfterEach
  void cleanUp() {
    jdbc.update("delete from catalog_collect_requests where brand = ?", brand);
    jdbc.update(
        "delete from product_name_aliases where product_id in (select id from products where"
            + " brand ilike ?)",
        "%" + brand);
    jdbc.update("delete from pouch_items where user_id = ?", user);
    jdbc.update(
        "delete from product_shade_colors where shade_id in (select s.id from product_shades s"
            + " join products p on p.id = s.product_id where p.brand = ?)",
        brand);
    jdbc.update(
        "delete from product_shades where product_id in (select id from products where brand = ?)",
        brand);
    jdbc.update(
        "delete from product_shades where product_id in (select id from products where brand ilike"
            + " ?)",
        "%" + brand);
    jdbc.update("delete from products where brand ilike ?", "%" + brand);
  }

  @Test
  void aResolvedRequestLinksTheItemAndShowsTheCatalogColorInsteadOfTheMembers() throws Exception {
    UUID item = register(user, "쥬시래스팅틴트", "01 니어", "#C0FFEE");
    UUID request = sendRequest();
    UUID product = product("쥬시 래스팅 틴트");
    UUID shade = shade(product, "01 니어", "#AA3344");
    long versionBefore = pouchVersion(user);

    collected(request).andExpect(jsonPath("$.status").value("RESOLVED"));

    Map<String, Object> row = item(item);
    assertThat(row)
        .containsEntry("registration_mode", "CATALOG")
        .containsEntry("product_id", product)
        .containsEntry("shade_id", shade)
        .containsEntry("name", "쥬시 래스팅 틴트")
        .containsEntry("color_hex", "#AA3344")
        .containsEntry("color_source", "CATALOG");
    assertThat(pouchVersion(user)).isEqualTo(versionBefore + 1);
    assertThat(linkResult(request)).isEqualTo("LINKED");
  }

  @Test
  void anItemEditedAfterTheRequestIsLeftAlone() throws Exception {
    UUID item = register(user, "쥬시 래스팅 틴트", "01 니어", null);
    UUID request = sendRequest();
    jdbc.update(
        "update pouch_items set updated_at = updated_at + interval '1 second' where id = ?", item);
    shade(product("쥬시 래스팅 틴트"), "01 니어", "#AA3344");

    collected(request).andExpect(jsonPath("$.status").value("RESOLVED"));

    assertThat(item(item)).containsEntry("registration_mode", "MANUAL");
    assertThat(linkResult(request)).isEqualTo("ITEM_CHANGED");
  }

  @Test
  void anItemWithoutAShadeIsNotGuessedIntoOne() throws Exception {
    UUID item = register(user, "쥬시 래스팅 틴트", null, null);
    UUID request = sendRequest();
    shade(product("쥬시 래스팅 틴트"), "01 니어", "#AA3344");

    collected(request).andExpect(jsonPath("$.status").value("RESOLVED"));

    assertThat(item(item)).containsEntry("registration_mode", "MANUAL");
    assertThat(linkResult(request)).isEqualTo("SHADE_REQUIRED");
  }

  @Test
  void aProductAlreadyInThePouchIsNotLinkedTwice() throws Exception {
    UUID item = register(user, "쥬시래스팅틴트", "01 니어", null);
    UUID request = sendRequest();
    UUID product = product("쥬시 래스팅 틴트");
    UUID shade = shade(product, "01 니어", "#AA3344");
    mockMvc
        .perform(
            write(
                user,
                """
                {"registrationMode":"CATALOG","type":"%s","productId":"%s","shadeId":"%s"}
                """
                    .formatted(TYPE, product, shade)))
        .andExpect(status().isCreated());

    collected(request).andExpect(jsonPath("$.status").value("RESOLVED"));

    assertThat(item(item)).containsEntry("registration_mode", "MANUAL");
    assertThat(linkResult(request)).isEqualTo("ALREADY_IN_POUCH");
  }

  @Test
  void aProductAlreadyInTheCatalogIsLinkedRightAtRegistrationWithItsColor() throws Exception {
    UUID product = product("쥬시 래스팅 틴트");
    UUID shade = shade(product, "01 니어", "#AA3344");

    UUID item = register(user, "쥬시래스팅 틴트", "01 니어", null);

    assertThat(item(item))
        .containsEntry("registration_mode", "CATALOG")
        .containsEntry("shade_id", shade)
        .containsEntry("color_hex", "#AA3344")
        .containsEntry("color_source", "CATALOG");
  }

  @Test
  void anOfficialNameThatDiffersBecomesAnAliasForTheLinkAndTheNextSearch() throws Exception {
    UUID item = register(user, "쥬시 래스팅 틴트", "01 니어", null);
    UUID request = sendRequest();
    UUID product = sourcedProduct("rom&nd " + brand, "더 쥬시 래스팅 틴트", "77");
    shade(product, "01 니어", "#AA3344");

    collectedSource(request, "77").andExpect(jsonPath("$.status").value("RESOLVED"));

    assertThat(item(item))
        .containsEntry("registration_mode", "CATALOG")
        .containsEntry("product_id", product)
        .containsEntry("name", "더 쥬시 래스팅 틴트");
    assertThat(
            jdbc.queryForObject(
                "select count(*) from product_name_aliases where product_id = ?",
                Long.class,
                product))
        .isEqualTo(1);
    mockMvc
        .perform(
            get("/v1/products")
                .param("category", CATEGORY)
                .param("type", TYPE)
                .param("brand", brand)
                .param("name", "쥬시래스팅 틴트")
                .with(
                    authentication(
                        UsernamePasswordAuthenticationToken.authenticated(
                            new AuthenticatedUser(user, "member@example.com"),
                            null,
                            List.of(new SimpleGrantedAuthority("ROLE_USER"))))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items[0].productId").value(product.toString()));
  }

  @Test
  void aBrandPrefixedSiteNameAndASpacelessShadeLinkRightAtRegistration() throws Exception {
    UUID product = sourcedProduct(brand, brand + " 더 쥬시 래스팅 틴트", "88");
    UUID shade = shade(product, "02 누카다미아", "#AA3344");

    UUID item = register(user, "더 쥬시 래스팅 틴트", "02누카다미아", null);

    assertThat(item(item))
        .containsEntry("registration_mode", "CATALOG")
        .containsEntry("product_id", product)
        .containsEntry("shade_id", shade)
        .containsEntry("shade_name", "02 누카다미아");
  }

  @Test
  void severalCollectedProductsLeaveNoAlias() throws Exception {
    UUID item = register(user, "쥬시 래스팅 틴트", "01 니어", null);
    UUID request = sendRequest();
    sourcedProduct(brand, "더 쥬시 래스팅 틴트", "77");
    sourcedProduct(brand, "쥬시 래스팅 틴트 세트", "78");

    collectedSources(request, "77", "78")
        .andExpect(jsonPath("$.status").value("UNRESOLVED"))
        .andExpect(jsonPath("$.reason").value("NOT_IN_CATALOG"));

    assertThat(item(item)).containsEntry("registration_mode", "MANUAL");
    assertThat(
            jdbc.queryForObject(
                "select count(*) from product_name_aliases where request_id = ?",
                Long.class,
                request))
        .isZero();
  }

  private UUID sourcedProduct(String productBrand, String name, String sourceId) {
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into products (id, brand, name, brand_normalized, name_normalized, category_code,"
            + " type_code, source, source_product_id, source_url, created_at, updated_at)"
            + " values (?, ?, ?, lower(?), lower(?), ?, ?, 'OFFICIAL:shop.example', ?, ?, now(),"
            + " now())",
        id,
        productBrand,
        name,
        productBrand,
        name,
        CATEGORY,
        TYPE,
        brand + "-" + sourceId,
        "https://shop.example/p/" + sourceId);
    return id;
  }

  private org.springframework.test.web.servlet.ResultActions collectedSource(
      UUID request, String sourceId) throws Exception {
    return collectedSources(request, sourceId);
  }

  private org.springframework.test.web.servlet.ResultActions collectedSources(
      UUID request, String... sourceIds) throws Exception {
    StringBuilder refs = new StringBuilder();
    for (int i = 0; i < sourceIds.length; i++) {
      if (i > 0) {
        refs.append(',');
      }
      refs.append(
          """
          {"itemKey":"%06d","source":"OFFICIAL:shop.example","sourceProductId":"%s",
           "sourceUrl":"https://shop.example/p/%s"}
          """
              .formatted(i + 1, brand + "-" + sourceIds[i], sourceIds[i]));
    }
    String body =
        """
        {"contractVersion":1,"jobId":"%s","status":"COLLECTED","reason":null,
         "resultFile":"20261112-000012-job-a.jsonl","runId":"r-1","importRunId":null,
         "products":[%s],"failedProducts":[],"finishedAt":"2026-11-12T09:03:10+09:00"}
        """
            .formatted(request, refs);
    return mockMvc.perform(
        post("/v1/internal/catalog/collect-jobs/" + request + "/result")
            .header(InternalTokenFilter.HEADER, TOKEN)
            .contentType(MediaType.APPLICATION_JSON)
            .content(body));
  }

  @Test
  void aNameSharedBySeriesProductsLinksToTheSeriesThatHasTheShade() throws Exception {
    UUID original = sourcedProduct(brand, brand + " 블러 퍼지 틴트 #오리지널", "91");
    UUID black = sourcedProduct(brand, brand + " 블러 퍼지 틴트 #블랙", "92");
    shade(original, "01 오리지널", "#BE5953");
    UUID blackShade = shade(black, "03 블랙", "#222222");
    aliasFor(original);
    aliasFor(black);

    UUID item = register(user, "블러 퍼지 틴트", "03블랙", null);

    assertThat(item(item))
        .containsEntry("registration_mode", "CATALOG")
        .containsEntry("product_id", black)
        .containsEntry("shade_id", blackShade);
  }

  @Test
  void aSecondSeriesCollectedForTheSameNameIsAddedAsAnAliasAndLinked() throws Exception {
    UUID original = sourcedProduct(brand, brand + " 블러 퍼지 틴트 #오리지널", "91");
    shade(original, "01 오리지널", "#BE5953");
    aliasFor(original);
    UUID item = register(user, "블러 퍼지 틴트", "03 블랙", null);
    UUID request = sendRequest();
    UUID black = sourcedProduct(brand, brand + " 블러 퍼지 틴트 #블랙", "92");
    UUID blackShade = shade(black, "03 블랙", "#222222");

    collectedSource(request, "92").andExpect(jsonPath("$.status").value("RESOLVED"));

    assertThat(item(item)).containsEntry("product_id", black).containsEntry("shade_id", blackShade);
    assertThat(
            jdbc.queryForObject(
                "select count(*) from product_name_aliases where product_id in (?, ?)",
                Long.class,
                original,
                black))
        .isEqualTo(2);
  }

  private void aliasFor(UUID product) {
    jdbc.update(
        "insert into product_name_aliases (id, type_code, brand_normalized, name_compact,"
            + " product_id, created_at) values (gen_random_uuid(), ?, lower(?), ?, ?, now())",
        TYPE,
        brand,
        "블러퍼지틴트",
        product);
  }

  private UUID register(UUID member, String name, String shadeName, String colorHex)
      throws Exception {
    String json =
        """
        {"registrationMode":"MANUAL","category":"%s","type":"%s","brand":"%s","name":"%s","shadeName":%s,"colorHex":%s}
        """
            .formatted(
                CATEGORY,
                TYPE,
                brand,
                name,
                shadeName == null ? "null" : "\"" + shadeName + "\"",
                colorHex == null ? "null" : "\"" + colorHex + "\"");
    String body =
        mockMvc
            .perform(write(member, json))
            .andExpect(status().isCreated())
            .andReturn()
            .getResponse()
            .getContentAsString();
    return UUID.fromString(com.jayway.jsonpath.JsonPath.read(body, "$.item.pouchItemId"));
  }

  /** 큐가 꺼져 QUEUED 로 남은 요청을 보낸 것으로 바꾼다. */
  private UUID sendRequest() {
    UUID id =
        jdbc.queryForObject(
            "select id from catalog_collect_requests where brand = ? and status = 'QUEUED'",
            UUID.class,
            brand);
    jdbc.update(
        "update catalog_collect_requests set status = 'SENT', sent_at = now() where id = ?", id);
    return id;
  }

  private org.springframework.test.web.servlet.ResultActions collected(UUID request)
      throws Exception {
    String body =
        """
        {"contractVersion":1,"jobId":"%s","status":"COLLECTED","reason":null,
         "resultFile":"20261112-000012-job-a.jsonl","runId":"r-1","importRunId":null,
         "products":[{"itemKey":"000001","source":"OFFICIAL:shop.example",
           "sourceProductId":"1","sourceUrl":"https://shop.example/p/1"}],
         "failedProducts":[],"finishedAt":"2026-11-12T09:03:10+09:00"}
        """
            .formatted(request);
    return mockMvc.perform(
        post("/v1/internal/catalog/collect-jobs/" + request + "/result")
            .header(InternalTokenFilter.HEADER, TOKEN)
            .contentType(MediaType.APPLICATION_JSON)
            .content(body));
  }

  private UUID product(String name) {
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into products (id, brand, name, brand_normalized, name_normalized, category_code,"
            + " type_code, created_at, updated_at) values (?, ?, ?, lower(?), lower(?), ?, ?, now(),"
            + " now())",
        id,
        brand,
        name,
        brand,
        name,
        CATEGORY,
        TYPE);
    return id;
  }

  private UUID shade(UUID product, String name, String hex) {
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into product_shades (id, product_id, name, name_normalized, sort_order, color_hex,"
            + " color_source, color_estimated, created_at, updated_at) values (?, ?, ?, lower(?), 1,"
            + " ?, 'TEST', true, now(), now())",
        id,
        product,
        name,
        name,
        hex);
    return id;
  }

  private Map<String, Object> item(UUID id) {
    return jdbc.queryForMap("select * from pouch_items where id = ?", id);
  }

  private String linkResult(UUID request) {
    return jdbc.queryForObject(
        "select link_result from catalog_collect_request_users where request_id = ?",
        String.class,
        request);
  }

  private long pouchVersion(UUID member) {
    return jdbc.queryForObject("select pouch_version from users where id = ?", Long.class, member);
  }

  private UUID member() {
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into users (id, email, provider, created_at, updated_at)"
            + " values (?, ?, 'LOCAL', now(), now())",
        id,
        id + "@example.com");
    return id;
  }

  private org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder write(
      UUID member, String json) {
    return post("/v1/users/me/pouch-items")
        .with(
            authentication(
                UsernamePasswordAuthenticationToken.authenticated(
                    new AuthenticatedUser(member, "member@example.com"),
                    null,
                    List.of(new SimpleGrantedAuthority("ROLE_USER")))))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content(json);
  }
}
