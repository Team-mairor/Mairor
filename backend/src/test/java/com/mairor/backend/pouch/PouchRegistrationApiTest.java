package com.mairor.backend.pouch;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.products.entity.ReviewStatus;
import com.mairor.backend.users.support.AuthenticatedUser;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
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

/** 내 파우치 등록 API 계약, 분기 검증, 인증·CSRF와 버전 반영을 PostgreSQL로 확인한다. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql,classpath:db/schema/executions.sql",
      "app.security.allowed-origins=http://localhost:3000"
    })
@AutoConfigureMockMvc
class PouchRegistrationApiTest {

  private static final String PATH = "/v1/users/me/pouch-items";

  @Autowired private MockMvc mockMvc;
  @Autowired private JdbcTemplate jdbc;

  private UUID userId;
  private String category;
  private String type;
  private String otherCategory;
  private String otherType;
  private String otherTypeInCategory;
  private final List<UUID> products = new ArrayList<>();

  @BeforeEach
  void setUp() {
    userId = UUID.randomUUID();
    String suffix = UUID.randomUUID().toString().replace("-", "").substring(0, 8).toUpperCase();
    category = "PCH" + suffix;
    type = category + "_TYPE";
    otherCategory = "PCHX" + suffix;
    otherType = otherCategory + "_TYPE";
    otherTypeInCategory = category + "_ALT";

    jdbc.update(
        "insert into users (id, email, provider, created_at, updated_at) values (?, ?, 'LOCAL', now(), now())",
        userId,
        userId + "@example.com");
    jdbc.update(
        "insert into product_categories values (?, '시험 분류', true, true, 1), (?, '도구 분류', false, false, 2)",
        category,
        otherCategory);
    jdbc.update(
        "insert into product_types values (?, ?, '시험 종류', 1), (?, ?, '다른 분류 종류', 1), (?, ?, '같은 분류 다른 종류', 2)",
        type,
        category,
        otherType,
        otherCategory,
        otherTypeInCategory,
        category);
  }

  @AfterEach
  void cleanUp() {
    jdbc.update("delete from pouch_items where user_id = ?", userId);
    for (UUID productId : products) {
      jdbc.update(
          "delete from product_shade_colors where shade_id in (select id from product_shades where product_id = ?)",
          productId);
      jdbc.update("delete from product_shades where product_id = ?", productId);
      jdbc.update("delete from products where id = ?", productId);
    }
    jdbc.update(
        "delete from product_types where code in (?, ?, ?)", type, otherType, otherTypeInCategory);
    jdbc.update("delete from product_categories where code in (?, ?)", category, otherCategory);
    jdbc.update("delete from users where id = ?", userId);
  }

  @Test
  void manualRegistrationTrimsDisplayTextStoresColorAndIncrementsVersion() throws Exception {
    String request =
        """
        {"registrationMode":"MANUAL","category":"%s","type":"%s","brand":"  Brand  ","name":"  Product Name  ","shadeName":" 01 Rose ","colorHex":"#a1b2c3"}
        """
            .formatted(category, type);

    mockMvc
        .perform(write(request))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.item.registrationMode").value("MANUAL"))
        .andExpect(jsonPath("$.item.brand").value("Brand"))
        .andExpect(jsonPath("$.item.name").value("Product Name"))
        .andExpect(jsonPath("$.item.shadeName").value("01 Rose"))
        .andExpect(jsonPath("$.item.productId").value((Object) null))
        .andExpect(jsonPath("$.item.color.colorSpace").value("sRGB"))
        .andExpect(jsonPath("$.item.color.hex").value("#A1B2C3"))
        .andExpect(jsonPath("$.item.color.source").value("USER_INPUT"))
        .andExpect(jsonPath("$.item.color.estimated").value(true))
        .andExpect(jsonPath("$.item.colorSource").value("USER_INPUT"))
        .andExpect(jsonPath("$.pouchVersion").value(1));
  }

  @Test
  void catalogRegistrationCopiesProductShadeAndCatalogColor() throws Exception {
    UUID[] selection = productWithShade("Brand", "Catalog Product", "02 Rose", "#123456", true);
    String request =
        """
        {"registrationMode":"CATALOG","type":"%s","productId":"%s","shadeId":"%s"}
        """
            .formatted(type, selection[0], selection[1]);

    mockMvc
        .perform(write(request))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.item.registrationMode").value("CATALOG"))
        .andExpect(jsonPath("$.item.productId").value(selection[0].toString()))
        .andExpect(jsonPath("$.item.shadeId").value(selection[1].toString()))
        .andExpect(jsonPath("$.item.brand").value("Brand"))
        .andExpect(jsonPath("$.item.name").value("Catalog Product"))
        .andExpect(jsonPath("$.item.category").value(category))
        .andExpect(jsonPath("$.item.type").value(type))
        .andExpect(jsonPath("$.item.shadeName").value("02 Rose"))
        .andExpect(jsonPath("$.item.color.hex").value("#123456"))
        .andExpect(jsonPath("$.item.color.source").value("CATALOG"))
        .andExpect(jsonPath("$.item.color.estimated").value(true))
        .andExpect(jsonPath("$.pouchVersion").value(1));
  }

  @Test
  void singleUsableSlotColorIsCopiedAsCatalogColorWithItsEstimatedFlag() throws Exception {
    UUID[] selection = productWithShade("Brand", "Slot Product", "01 Slot", null, false);
    insertSlot(selection[1], 1, "#AB1234", "AUTO_APPROVED", true);

    mockMvc
        .perform(write(catalogRequest(selection)))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.item.color.hex").value("#AB1234"))
        .andExpect(jsonPath("$.item.color.source").value("CATALOG"))
        .andExpect(jsonPath("$.item.color.estimated").value(true))
        .andExpect(jsonPath("$.item.colorSource").value("CATALOG"));
  }

  @Test
  void slotsDecideTheColorEvenWhenTheOldShadeColorIsStillThere() throws Exception {
    UUID[] selection = productWithShade("Brand", "Slot Wins", "01 Slot", "#111111", false);
    insertSlot(selection[1], 1, "#222222", "AUTO_APPROVED", false);

    mockMvc
        .perform(write(catalogRequest(selection)))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.item.color.hex").value("#222222"))
        .andExpect(jsonPath("$.item.color.estimated").value(false));
  }

  @Test
  void aSlotBelowThresholdGivesNoColorAndTheOldShadeColorIsNotUsedInsteadOfIt() throws Exception {
    UUID[] selection = productWithShade("Brand", "Below", "01 Below", "#111111", false);
    insertSlot(selection[1], 1, "#222222", "BELOW_THRESHOLD", true);

    mockMvc
        .perform(write(catalogRequest(selection)))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.item.color").value(org.hamcrest.Matchers.nullValue()))
        .andExpect(jsonPath("$.item.colorSource").value("NONE"));
  }

  @Test
  void aPaletteWithSeveralSlotsStoresNoColorButShowsTheFirstSlotAsPreview() throws Exception {
    UUID[] selection = productWithShade("Brand", "Palette", "01 Palette", null, false);
    insertSlot(selection[1], 1, "#AA0000", "AUTO_APPROVED", true);
    insertSlot(selection[1], 2, "#00AA00", "AUTO_APPROVED", true);

    mockMvc
        .perform(write(catalogRequest(selection)))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.item.color.hex").value("#AA0000"))
        .andExpect(jsonPath("$.item.colorSource").value("CATALOG"));

    assertThat(
            jdbc.queryForObject(
                "select color_hex from pouch_items where product_id = ?",
                String.class,
                selection[0]))
        .isNull();
  }

  @Test
  void aSlotWithoutAnyColorGivesNoColor() throws Exception {
    UUID[] selection = productWithShade("Brand", "Empty Slot", "01 Empty", null, false);
    jdbc.update(
        "insert into product_shade_colors (id, shade_id, sort_order, name_source, created_at, updated_at) values (?, ?, 1, 'NONE', now(), now())",
        UUID.randomUUID(),
        selection[1]);

    mockMvc
        .perform(write(catalogRequest(selection)))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.item.color").value(org.hamcrest.Matchers.nullValue()));
  }

  /** SQL 의 쓸 수 있는 상태 목록이 {@link ReviewStatus#isUsable}과 어긋나지 않는지 모든 값으로 확인한다. */
  @ParameterizedTest
  @EnumSource(ReviewStatus.class)
  void theSlotStatusesTheQueryAcceptsMatchReviewStatusUsable(ReviewStatus reviewStatus)
      throws Exception {
    UUID[] selection = productWithShade("Brand", "Status " + reviewStatus, "01 S", null, false);
    insertSlot(selection[1], 1, "#345678", reviewStatus.name(), false);

    var result = mockMvc.perform(write(catalogRequest(selection))).andExpect(status().isCreated());

    if (reviewStatus.isUsable()) {
      result.andExpect(jsonPath("$.item.color.hex").value("#345678"));
    } else {
      result.andExpect(jsonPath("$.item.color").value(org.hamcrest.Matchers.nullValue()));
    }
  }

  @Test
  void manualRegistrationWithoutShadeOrColorReturnsNullColorSourceNone() throws Exception {
    mockMvc
        .perform(write(manualRequest(category, type, "Brand", "Tool", null, null)))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.item.shadeName").value((Object) null))
        .andExpect(jsonPath("$.item.color").value((Object) null))
        .andExpect(jsonPath("$.item.colorSource").value("NONE"));
  }

  @Test
  void invalidCatalogSelectionAndManualCategoryTypePairDoNotIncrementVersion() throws Exception {
    UUID[] product = productWithShade("Brand", "Catalog Product", "01", null, false);
    String noShade =
        """
        {"registrationMode":"CATALOG","type":"%s","productId":"%s"}
        """
            .formatted(type, product[0]);
    mockMvc
        .perform(write(noShade))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("POUCH_INVALID_PRODUCT"));

    String wrongPair = manualRequest(category, otherType, "Brand", "Wrong pair", null, null);
    mockMvc
        .perform(write(wrongPair))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("POUCH_INVALID_PRODUCT"));

    assertThatVersionIs(0L);
  }

  @Test
  void invalidManualTextAndColorReturnValidationFailedWithoutSaving() throws Exception {
    String badHex = manualRequest(category, type, "Brand", "Bad color", null, "red");
    mockMvc
        .perform(write(badHex))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value("colorHex"));

    String longName = manualRequest(category, type, "Brand", "N".repeat(201), null, null);
    mockMvc
        .perform(write(longName))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("name"));

    assertThatVersionIs(0L);
  }

  @Test
  void duplicateAcrossTypesReturnsConflictAndDoesNotIncrementAgain() throws Exception {
    mockMvc
        .perform(write(manualRequest(category, type, "Brand  One", "Product Name", null, null)))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.pouchVersion").value(1));

    mockMvc
        .perform(
            write(
                manualRequest(
                    category, otherTypeInCategory, "brand one", "Product   Name", " ", null)))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("POUCH_DUPLICATE"));

    assertThatVersionIs(1L);
  }

  @Test
  void registrationRequiresAuthenticationAndCsrf() throws Exception {
    mockMvc
        .perform(post(PATH).contentType(MediaType.APPLICATION_JSON).content("{}"))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("CSRF_INVALID"));

    mockMvc
        .perform(post(PATH).with(csrf()).contentType(MediaType.APPLICATION_JSON).content("{}"))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
  }

  private org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder write(
      String json) {
    return post(PATH)
        .with(asMember(userId))
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

  private String manualRequest(
      String categoryCode,
      String typeCode,
      String brand,
      String name,
      String shadeName,
      String colorHex) {
    return """
        {"registrationMode":"MANUAL","category":"%s","type":"%s","brand":"%s","name":"%s","shadeName":%s,"colorHex":%s}
        """
        .formatted(
            categoryCode,
            typeCode,
            brand,
            name,
            shadeName == null ? "null" : "\"" + shadeName + "\"",
            colorHex == null ? "null" : "\"" + colorHex + "\"");
  }

  private UUID[] productWithShade(
      String brand, String name, String shadeName, String colorHex, boolean estimated) {
    UUID productId = UUID.randomUUID();
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
    if (shadeName == null) return new UUID[] {productId, null};
    UUID shadeId = UUID.randomUUID();
    if (colorHex == null) {
      jdbc.update(
          "insert into product_shades (id, product_id, name, name_normalized, sort_order, created_at, updated_at) values (?, ?, ?, ?, 1, now(), now())",
          shadeId,
          productId,
          shadeName,
          shadeName.toLowerCase());
    } else {
      jdbc.update(
          "insert into product_shades (id, product_id, name, name_normalized, sort_order, color_hex, color_source, color_estimated, created_at, updated_at) values (?, ?, ?, ?, 1, ?, 'TEST', ?, now(), now())",
          shadeId,
          productId,
          shadeName,
          shadeName.toLowerCase(),
          colorHex,
          estimated);
    }
    return new UUID[] {productId, shadeId};
  }

  private String catalogRequest(UUID[] selection) {
    return """
        {"registrationMode":"CATALOG","type":"%s","productId":"%s","shadeId":"%s"}
        """
        .formatted(type, selection[0], selection[1]);
  }

  private void insertSlot(
      UUID shadeId, int sortOrder, String hex, String reviewStatus, boolean estimated) {
    jdbc.update(
        "insert into product_shade_colors (id, shade_id, sort_order, name_source, color_hex, color_source, color_estimated, review_status, created_at, updated_at) values (?, ?, ?, 'NONE', ?, 'PRODUCT_PHOTO', ?, ?, now(), now())",
        UUID.randomUUID(),
        shadeId,
        sortOrder,
        hex,
        estimated,
        reviewStatus);
  }

  private void assertThatVersionIs(long expected) {
    Long actual =
        jdbc.queryForObject("select pouch_version from users where id = ?", Long.class, userId);
    org.assertj.core.api.Assertions.assertThat(actual).isEqualTo(expected);
  }
}
