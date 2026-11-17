package com.mairor.backend.pouch;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.users.support.AuthenticatedUser;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
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
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.request.RequestPostProcessor;

/** 내 파우치 수정 API의 병합, 전환, 소유권과 버전 계약을 PostgreSQL로 확인한다. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql,classpath:db/schema/executions.sql",
      "app.security.allowed-origins=http://localhost:3000"
    })
@AutoConfigureMockMvc
class PouchUpdateApiTest {

  private static final String PATH = "/v1/users/me/pouch-items";

  @Autowired private MockMvc mockMvc;
  @Autowired private JdbcTemplate jdbc;

  private UUID userId;
  private UUID otherUserId;
  private String category;
  private String type;
  private String toolCategory;
  private String toolType;
  private final List<UUID> products = new ArrayList<>();

  @BeforeEach
  void setUp() {
    userId = UUID.randomUUID();
    otherUserId = UUID.randomUUID();
    String suffix = UUID.randomUUID().toString().replace("-", "").substring(0, 8).toUpperCase();
    category = "PUA" + suffix;
    type = category + "_TYPE";
    toolCategory = "PUT" + suffix;
    toolType = toolCategory + "_TYPE";

    for (UUID id : List.of(userId, otherUserId)) {
      jdbc.update(
          "insert into users (id, email, provider, created_at, updated_at) values (?, ?, 'LOCAL', now(), now())",
          id,
          id + "@example.com");
    }
    jdbc.update(
        "insert into product_categories values (?, '시험 분류', true, true, 1), (?, '도구 분류', true, false, 2)",
        category,
        toolCategory);
    jdbc.update(
        "insert into product_types values (?, ?, '시험 종류', 1), (?, ?, '도구 종류', 1)",
        type,
        category,
        toolType,
        toolCategory);
  }

  @AfterEach
  void cleanUp() {
    jdbc.update("delete from pouch_items where user_id in (?, ?)", userId, otherUserId);
    for (UUID productId : products) {
      jdbc.update(
          "delete from product_shade_colors where shade_id in (select id from product_shades where product_id = ?)",
          productId);
      jdbc.update("delete from product_shades where product_id = ?", productId);
      jdbc.update("delete from products where id = ?", productId);
    }
    jdbc.update("delete from product_types where code in (?, ?)", type, toolType);
    jdbc.update("delete from product_categories where code in (?, ?)", category, toolCategory);
    jdbc.update("delete from users where id in (?, ?)", userId, otherUserId);
  }

  @Test
  void manualPatchMergesFieldsClearsNullableValuesAndKeepsVersionForNoop() throws Exception {
    UUID itemId = registerManual(userId, category, type, "Brand", "Original", "01 Rose", "#AABBCC");

    mockMvc
        .perform(update(userId, itemId, "{\"name\":\"Updated\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.item.name").value("Updated"))
        .andExpect(jsonPath("$.item.brand").value("Brand"))
        .andExpect(jsonPath("$.item.shadeName").value("01 Rose"))
        .andExpect(jsonPath("$.item.color.hex").value("#AABBCC"))
        .andExpect(jsonPath("$.pouchVersion").value(2));

    MvcResult cleared =
        mockMvc
            .perform(update(userId, itemId, "{\"shadeName\":null,\"colorHex\":null}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.item.shadeName").value((Object) null))
            .andExpect(jsonPath("$.item.color").value((Object) null))
            .andExpect(jsonPath("$.item.colorSource").value("NONE"))
            .andExpect(jsonPath("$.pouchVersion").value(3))
            .andReturn();
    String updatedAt =
        JsonPath.read(cleared.getResponse().getContentAsString(), "$.item.updatedAt");

    mockMvc
        .perform(update(userId, itemId, "{\"name\":\"Updated\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.pouchVersion").value(3))
        .andExpect(jsonPath("$.item.updatedAt").value(updatedAt));

    mockMvc
        .perform(update(userId, itemId, "{}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("POUCH_INVALID_UPDATE"));

    mockMvc
        .perform(update(userId, itemId, "{\"category\":null}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value("category"));

    assertVersion(3L);
  }

  @Test
  void catalogDirectEditSwitchesToManualAndDoesNotCarryCatalogColor() throws Exception {
    ProductSelection selection =
        productWithShade("Catalog Brand", "Catalog Product", "02 Rose", "#123456");
    UUID itemId = registerCatalog(userId, selection);

    mockMvc
        .perform(update(userId, itemId, "{\"name\":\"Personal Name\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.item.registrationMode").value("MANUAL"))
        .andExpect(jsonPath("$.item.productId").value((Object) null))
        .andExpect(jsonPath("$.item.shadeId").value((Object) null))
        .andExpect(jsonPath("$.item.name").value("Personal Name"))
        .andExpect(jsonPath("$.item.shadeName").value("02 Rose"))
        .andExpect(jsonPath("$.item.color").value((Object) null))
        .andExpect(jsonPath("$.item.colorSource").value("NONE"))
        .andExpect(jsonPath("$.pouchVersion").value(2));

    assertVersion(2L);
  }

  @Test
  void manualToCatalogRequiresNewShadeWhenChangingToShadeSelectableProduct() throws Exception {
    UUID itemId = registerManual(userId, category, type, "Manual Brand", "Manual Item", null, null);
    ProductSelection first = productWithShade("Catalog Brand", "First Product", "01", "#111111");
    ProductSelection second = productWithShade("Other Brand", "Second Product", "02", "#222222");

    mockMvc
        .perform(
            update(
                userId,
                itemId,
                "{\"registrationMode\":\"CATALOG\",\"productId\":\""
                    + first.productId()
                    + "\",\"type\":\""
                    + type
                    + "\",\"shadeId\":\""
                    + first.shadeId()
                    + "\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.item.registrationMode").value("CATALOG"))
        .andExpect(jsonPath("$.item.productId").value(first.productId().toString()))
        .andExpect(jsonPath("$.item.color.source").value("CATALOG"))
        .andExpect(jsonPath("$.pouchVersion").value(2));

    mockMvc
        .perform(update(userId, itemId, "{\"productId\":\"" + second.productId() + "\"}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("POUCH_INVALID_UPDATE"));
    assertVersion(2L);

    mockMvc
        .perform(
            update(
                userId,
                itemId,
                "{\"productId\":\""
                    + second.productId()
                    + "\",\"shadeId\":\""
                    + second.shadeId()
                    + "\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.item.productId").value(second.productId().toString()))
        .andExpect(jsonPath("$.item.shadeId").value(second.shadeId().toString()))
        .andExpect(jsonPath("$.item.name").value("Second Product"))
        .andExpect(jsonPath("$.pouchVersion").value(3));

    assertVersion(3L);
  }

  @Test
  void changingTheCatalogShadeRecomputesTheColorFromTheNewShadesSlots() throws Exception {
    UUID itemId = registerManual(userId, category, type, "Manual Brand", "Manual Item", null, null);
    ProductSelection single = productWithShade("Brand", "Single", "01", "#111111");
    ProductSelection palette = productWithShade("Brand", "Palette", "02", "#222222");
    insertSlot(single.shadeId(), 1, "#ABCDEF", "AUTO_APPROVED");
    insertSlot(palette.shadeId(), 1, "#AA0000", "AUTO_APPROVED");
    insertSlot(palette.shadeId(), 2, "#00AA00", "AUTO_APPROVED");

    mockMvc
        .perform(
            update(
                userId,
                itemId,
                "{\"registrationMode\":\"CATALOG\",\"productId\":\""
                    + single.productId()
                    + "\",\"type\":\""
                    + type
                    + "\",\"shadeId\":\""
                    + single.shadeId()
                    + "\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.item.color.hex").value("#ABCDEF"))
        .andExpect(jsonPath("$.item.color.source").value("CATALOG"));

    mockMvc
        .perform(
            update(
                userId,
                itemId,
                "{\"productId\":\""
                    + palette.productId()
                    + "\",\"shadeId\":\""
                    + palette.shadeId()
                    + "\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.item.color.hex").value("#AA0000"))
        .andExpect(jsonPath("$.item.colorSource").value("CATALOG"));
    assertThat(
            jdbc.queryForObject(
                "select color_hex from pouch_items where id = ?", String.class, itemId))
        .isNull();
  }

  @Test
  void sameCatalogValuesIncludingFullFormKeepCatalogLinkAndVersion() throws Exception {
    ProductSelection selection =
        productWithShade("Catalog Brand", "Catalog Product", "02 Rose", "#12ABCD");
    UUID itemId = registerCatalog(userId, selection);
    String updatedAtBefore =
        jdbc.queryForObject(
            "select updated_at::text from pouch_items where id = ?", String.class, itemId);

    mockMvc
        .perform(
            update(
                userId,
                itemId,
                "{\"category\":\""
                    + category
                    + "\",\"type\":\""
                    + type
                    + "\",\"brand\":\"Catalog Brand\",\"name\":\"Catalog Product\",\"shadeName\":\"02 Rose\",\"colorHex\":\"#12abcd\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.item.registrationMode").value("CATALOG"))
        .andExpect(jsonPath("$.item.productId").value(selection.productId().toString()))
        .andExpect(jsonPath("$.item.shadeId").value(selection.shadeId().toString()))
        .andExpect(jsonPath("$.item.color.hex").value("#12ABCD"))
        .andExpect(jsonPath("$.item.color.source").value("CATALOG"))
        .andExpect(jsonPath("$.pouchVersion").value(1));

    assertVersion(1L);
    assertThat(
            jdbc.queryForObject(
                "select updated_at::text from pouch_items where id = ?", String.class, itemId))
        .isEqualTo(updatedAtBefore);
  }

  @Test
  void sameCatalogIdsKeepSavedCopyAndDirectColorEditSwitchesToManual() throws Exception {
    ProductSelection selection =
        productWithShade("Catalog Brand", "Catalog Product", "02 Rose", "#123456");
    UUID itemId = registerCatalog(userId, selection);
    jdbc.update(
        "update products set brand = ?, brand_normalized = ?, name = ?, name_normalized = ? where id = ?",
        "Changed Brand",
        "changed brand",
        "Changed Product",
        "changed product",
        selection.productId());
    jdbc.update(
        "update product_shades set name = ?, name_normalized = ?, color_hex = ? where id = ?",
        "Changed Shade",
        "changed shade",
        "#654321",
        selection.shadeId());

    mockMvc
        .perform(
            update(
                userId,
                itemId,
                "{\"productId\":\""
                    + selection.productId()
                    + "\",\"shadeId\":\""
                    + selection.shadeId()
                    + "\",\"type\":\""
                    + type
                    + "\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.item.registrationMode").value("CATALOG"))
        .andExpect(jsonPath("$.item.brand").value("Catalog Brand"))
        .andExpect(jsonPath("$.item.name").value("Catalog Product"))
        .andExpect(jsonPath("$.item.shadeName").value("02 Rose"))
        .andExpect(jsonPath("$.item.color.hex").value("#123456"))
        .andExpect(jsonPath("$.pouchVersion").value(1));

    mockMvc
        .perform(update(userId, itemId, "{\"colorHex\":\"#ABCDEF\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.item.registrationMode").value("MANUAL"))
        .andExpect(jsonPath("$.item.shadeName").value("02 Rose"))
        .andExpect(jsonPath("$.item.color.hex").value("#ABCDEF"))
        .andExpect(jsonPath("$.item.color.source").value("USER_INPUT"))
        .andExpect(jsonPath("$.item.color.estimated").value(true))
        .andExpect(jsonPath("$.pouchVersion").value(2));
  }

  @Test
  void explicitCatalogToManualTransitionRequiresAllManualRequiredFields() throws Exception {
    ProductSelection selection =
        productWithShade("Catalog Brand", "Catalog Product", "01 Rose", "#123456");
    UUID itemId = registerCatalog(userId, selection);

    mockMvc
        .perform(update(userId, itemId, "{\"registrationMode\":\"MANUAL\"}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("POUCH_INVALID_UPDATE"));
    assertVersion(1L);

    String request =
        "{\"registrationMode\":\"MANUAL\",\"category\":\""
            + category
            + "\",\"type\":\""
            + type
            + "\",\"brand\":\"Manual Brand\",\"name\":\"Manual Name\"}";
    mockMvc
        .perform(update(userId, itemId, request))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.item.registrationMode").value("MANUAL"))
        .andExpect(jsonPath("$.item.productId").value((Object) null))
        .andExpect(jsonPath("$.item.shadeName").value((Object) null))
        .andExpect(jsonPath("$.item.color").value((Object) null))
        .andExpect(jsonPath("$.item.colorSource").value("NONE"))
        .andExpect(jsonPath("$.pouchVersion").value(2));
  }

  @Test
  void catalogTransitionWithMismatchedTypeDoesNotChangeItemOrVersion() throws Exception {
    UUID itemId = registerManual(userId, category, type, "Manual Brand", "Manual Name", null, null);
    ProductSelection selection =
        productWithShade("Catalog Brand", "Catalog Product", "01", "#123456");
    String request =
        "{\"registrationMode\":\"CATALOG\",\"productId\":\""
            + selection.productId()
            + "\",\"type\":\""
            + toolType
            + "\",\"shadeId\":\""
            + selection.shadeId()
            + "\"}";

    mockMvc
        .perform(update(userId, itemId, request))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("POUCH_INVALID_PRODUCT"));

    assertVersion(1L);
    assertThat(
            jdbc.queryForObject("select name from pouch_items where id = ?", String.class, itemId))
        .isEqualTo("Manual Name");
  }

  @Test
  void duplicateUpdateReturnsConflictWithoutChangingItemOrVersion() throws Exception {
    UUID first = registerManual(userId, category, type, "Brand", "First", "01", null);
    registerManual(userId, category, type, "Brand", "Second", "01", null);

    mockMvc
        .perform(update(userId, first, "{\"name\":\"second\"}"))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("POUCH_DUPLICATE"));

    assertVersion(2L);
    assertThat(
            jdbc.queryForObject("select name from pouch_items where id = ?", String.class, first))
        .isEqualTo("First");
  }

  @Test
  void movingManualItemToCategoryWithoutShadesClearsShadeAndColor() throws Exception {
    UUID itemId = registerManual(userId, category, type, "Brand", "Brush", "01 Rose", "#AABBCC");

    mockMvc
        .perform(
            update(
                userId,
                itemId,
                "{\"category\":\"" + toolCategory + "\",\"type\":\"" + toolType + "\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.item.category").value(toolCategory))
        .andExpect(jsonPath("$.item.type").value(toolType))
        .andExpect(jsonPath("$.item.shadeName").value((Object) null))
        .andExpect(jsonPath("$.item.color").value((Object) null))
        .andExpect(jsonPath("$.item.colorSource").value("NONE"))
        .andExpect(jsonPath("$.pouchVersion").value(2));
  }

  @Test
  void concurrentPatchesToDifferentFieldsAreMergedAndBothIncrementVersion() throws Exception {
    UUID itemId = registerManual(userId, category, type, "Brand", "Original", "01 Rose", "#AABBCC");
    CountDownLatch start = new CountDownLatch(1);

    try (var pool = Executors.newFixedThreadPool(2)) {
      Future<String> nameUpdate =
          pool.submit(
              () -> {
                assertThat(start.await(10, TimeUnit.SECONDS)).isTrue();
                return mockMvc
                    .perform(update(userId, itemId, "{\"name\":\"Concurrent Name\"}"))
                    .andExpect(status().isOk())
                    .andReturn()
                    .getResponse()
                    .getContentAsString();
              });
      Future<String> shadeUpdate =
          pool.submit(
              () -> {
                assertThat(start.await(10, TimeUnit.SECONDS)).isTrue();
                return mockMvc
                    .perform(update(userId, itemId, "{\"shadeName\":\"02 Rose\"}"))
                    .andExpect(status().isOk())
                    .andReturn()
                    .getResponse()
                    .getContentAsString();
              });
      start.countDown();
      String nameResponse = nameUpdate.get(20, TimeUnit.SECONDS);
      String shadeResponse = shadeUpdate.get(20, TimeUnit.SECONDS);
      assertThat(JsonPath.read(nameResponse, "$.pouchVersion").toString()).isIn("2", "3");
      assertThat(JsonPath.read(shadeResponse, "$.pouchVersion").toString()).isIn("2", "3");
    }

    assertThat(
            jdbc.queryForObject("select name from pouch_items where id = ?", String.class, itemId))
        .isEqualTo("Concurrent Name");
    assertThat(
            jdbc.queryForObject(
                "select shade_name from pouch_items where id = ?", String.class, itemId))
        .isEqualTo("02 Rose");
    assertVersion(3L);
  }

  @Test
  void otherMembersItemsAreHiddenAndAuthenticationAndCsrfAreRequired() throws Exception {
    UUID otherItem = registerManual(otherUserId, category, type, "Other", "Private", null, null);

    mockMvc
        .perform(update(userId, otherItem, "{\"name\":\"Changed\"}"))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOT_FOUND"));

    mockMvc
        .perform(update(userId, UUID.randomUUID(), "{\"name\":\"Changed\"}"))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOT_FOUND"));

    mockMvc
        .perform(
            patch(PATH + "/" + otherItem)
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Changed\"}"))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));

    mockMvc
        .perform(
            patch(PATH + "/" + otherItem)
                .with(asMember(userId))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Changed\"}"))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("CSRF_INVALID"));
  }

  private UUID registerManual(
      UUID owner,
      String categoryCode,
      String typeCode,
      String brand,
      String name,
      String shadeName,
      String colorHex)
      throws Exception {
    String request =
        """
        {"registrationMode":"MANUAL","category":"%s","type":"%s","brand":"%s","name":"%s","shadeName":%s,"colorHex":%s}
        """
            .formatted(
                categoryCode, typeCode, brand, name, jsonString(shadeName), jsonString(colorHex));
    MvcResult result =
        mockMvc.perform(register(owner, request)).andExpect(status().isCreated()).andReturn();
    return UUID.fromString(
        JsonPath.read(result.getResponse().getContentAsString(), "$.item.pouchItemId"));
  }

  private UUID registerCatalog(UUID owner, ProductSelection selection) throws Exception {
    String request =
        """
        {"registrationMode":"CATALOG","type":"%s","productId":"%s","shadeId":"%s"}
        """
            .formatted(type, selection.productId(), selection.shadeId());
    MvcResult result =
        mockMvc.perform(register(owner, request)).andExpect(status().isCreated()).andReturn();
    return UUID.fromString(
        JsonPath.read(result.getResponse().getContentAsString(), "$.item.pouchItemId"));
  }

  private MockHttpServletRequestBuilder register(UUID owner, String json) {
    return post(PATH)
        .with(asMember(owner))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content(json);
  }

  private MockHttpServletRequestBuilder update(UUID owner, UUID itemId, String json) {
    return patch(PATH + "/" + itemId)
        .with(asMember(owner))
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

  private ProductSelection productWithShade(
      String brand, String name, String shadeName, String colorHex) {
    UUID productId = UUID.randomUUID();
    UUID shadeId = UUID.randomUUID();
    products.add(productId);
    jdbc.update(
        "insert into products (id, brand, name, brand_normalized, name_normalized, category_code, type_code, created_at, updated_at) values (?, ?, ?, ?, ?, ?, ?, now(), now())",
        productId,
        brand,
        name,
        brand.toLowerCase(),
        name.toLowerCase(),
        category,
        type);
    jdbc.update(
        "insert into product_shades (id, product_id, name, name_normalized, sort_order, color_hex, color_source, color_estimated, created_at, updated_at) values (?, ?, ?, ?, 1, ?, 'TEST', true, now(), now())",
        shadeId,
        productId,
        shadeName,
        shadeName.toLowerCase(),
        colorHex);
    return new ProductSelection(productId, shadeId);
  }

  private void insertSlot(UUID shadeId, int sortOrder, String hex, String reviewStatus) {
    jdbc.update(
        "insert into product_shade_colors (id, shade_id, sort_order, name_source, color_hex, color_source, color_estimated, review_status, created_at, updated_at) values (?, ?, ?, 'NONE', ?, 'PRODUCT_PHOTO', false, ?, now(), now())",
        UUID.randomUUID(),
        shadeId,
        sortOrder,
        hex,
        reviewStatus);
  }

  private void assertVersion(long expected) {
    Long actual =
        jdbc.queryForObject("select pouch_version from users where id = ?", Long.class, userId);
    assertThat(actual).isEqualTo(expected);
  }

  private static String jsonString(String value) {
    return value == null ? "null" : "\"" + value + "\"";
  }

  private record ProductSelection(UUID productId, UUID shadeId) {}
}
