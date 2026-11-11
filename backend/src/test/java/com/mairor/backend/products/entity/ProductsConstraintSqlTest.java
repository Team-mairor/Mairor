package com.mairor.backend.products.entity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.TestcontainersConfiguration;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

/**
 * 스키마 SQL({@code db/schema/products.sql})의 제약과 인덱스를 SQL 로 직접 넣어 확인한다. 엔티티를 거치지 않은 데이터도 DB 가 막아야 하는
 * 규칙들이다. 반대로 앱에서만 지키는 규칙(호수 선택 불가 카테고리)은 DB 가 막지 않는다는 것도 함께 남긴다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql",
      "app.security.allowed-origins=http://localhost:3000"
    })
@Transactional
class ProductsConstraintSqlTest {

  private static final String TINT_ID = "00000000-0000-4000-8000-000000000001";
  private static final String TONER_ID = "00000000-0000-4000-8000-000000000002";

  private static final String INSERT_PRODUCT =
      "insert into products (id, brand, name, brand_normalized, name_normalized, category_code,"
          + " type_code, created_at, updated_at) values (?::uuid, ?, ?, ?, ?, ?, ?, now(), now())";
  private static final String INSERT_SHADE =
      "insert into product_shades (id, product_id, name, name_normalized, sort_order, color_hex,"
          + " color_source, color_estimated, created_at, updated_at)"
          + " values (gen_random_uuid(), ?::uuid, ?, ?, 1, ?, ?, ?, now(), now())";

  private static final String INSERT_ALIAS =
      "insert into product_shade_option_aliases (shade_id, source_option_id) values (?::uuid, ?)";
  private static final String INSERT_SLOT =
      "insert into product_shade_colors (id, shade_id, sort_order, name, name_normalized,"
          + " name_source, color_hex, color_source, color_estimated, review_status, created_at,"
          + " updated_at) values (gen_random_uuid(), ?::uuid, ?, ?, ?, ?, ?, ?, ?, ?, now(), now())";

  @Autowired private JdbcTemplate jdbc;

  @BeforeEach
  void setUp() {
    update(
        "insert into product_categories (code, label, matchable, shade_selectable, sort_order)"
            + " values ('LIP', '립', true, true, 5), ('SKINCARE', '스킨케어', false, false, 6)");
    update(
        "insert into product_types (code, category_code, label, sort_order)"
            + " values ('LIP_TINT', 'LIP', '립틴트', 3), ('TONER', 'SKINCARE', '토너', 1)");
    update(INSERT_PRODUCT, TINT_ID, "ETUDE", "Tint", "etude", "tint", "LIP", "LIP_TINT");
    update(INSERT_PRODUCT, TONER_ID, "ETUDE", "Toner", "etude", "toner", "SKINCARE", "TONER");
  }

  // --- 제약 이름 ---

  @Test
  void constraintsUseTheNamesTheCodeDependsOn() {
    assertThat(constraints("product_types"))
        .contains("product_types_pkey", ProductType.CATEGORY_FK, ProductType.CATEGORY_CODE_UNIQUE);
    assertThat(constraints("product_category_parts"))
        .contains("product_category_parts_pkey", ProductCategory.PARTS_CATEGORY_FK);
    assertThat(constraints("products"))
        .contains("products_pkey", Product.CATEGORY_TYPE_FK, Product.TYPE_BRAND_NAME_UNIQUE);
    assertThat(constraints("product_shades"))
        .contains(
            "product_shades_pkey",
            ProductShade.PRODUCT_FK,
            ProductShade.PRODUCT_NAME_UNIQUE,
            ProductShade.COLOR_ALL_OR_NONE_CHECK,
            ProductShade.COLOR_HEX_CHECK);
    assertThat(constraints("products")).contains(Product.SALE_STATUS_CHECK);
    assertThat(constraints("product_shade_option_aliases"))
        .contains("product_shade_option_aliases_pkey", ProductShade.OPTION_ALIAS_FK);
    assertThat(constraints("product_shade_colors"))
        .contains(
            "product_shade_colors_pkey",
            ProductShadeColor.SHADE_FK,
            ProductShadeColor.SHADE_ORDER_UNIQUE,
            ProductShadeColor.NAME_PAIR_CHECK,
            ProductShadeColor.NAME_SOURCE_CHECK,
            ProductShadeColor.COLOR_ALL_OR_NONE_CHECK,
            ProductShadeColor.COLOR_HEX_CHECK,
            ProductShadeColor.COLOR_SOURCE_CHECK,
            ProductShadeColor.REVIEW_CHECK);
  }

  // --- 카테고리·종류 ---

  @Test
  void productWhoseCategoryDoesNotMatchItsTypeIsRejected() {
    // 립 카테고리 + 토너 종류
    assertThatThrownBy(
            () ->
                update(
                    INSERT_PRODUCT,
                    "00000000-0000-4000-8000-000000000009",
                    "ETUDE",
                    "Mismatch",
                    "etude",
                    "mismatch",
                    "LIP",
                    "TONER"))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(Product.CATEGORY_TYPE_FK);
  }

  @Test
  void productWithAnUnknownTypeIsRejected() {
    assertThatThrownBy(
            () ->
                update(
                    INSERT_PRODUCT,
                    "00000000-0000-4000-8000-000000000009",
                    "ETUDE",
                    "Unknown",
                    "etude",
                    "unknown",
                    "LIP",
                    "LIP_UNKNOWN"))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(Product.CATEGORY_TYPE_FK);
  }

  @Test
  void typeAndCompatiblePartMustReferenceAnExistingCategory() {
    assertThatThrownBy(
            () ->
                update(
                    "insert into product_types (code, category_code, label, sort_order)"
                        + " values ('X', 'NOPE', 'x', 1)"))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(ProductType.CATEGORY_FK);
    assertThatThrownBy(
            () ->
                update(
                    "insert into product_category_parts (category_code, part_code)"
                        + " values ('NOPE', 'P1')"))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(ProductCategory.PARTS_CATEGORY_FK);
  }

  // --- 중복 ---

  @Test
  void sameTypeBrandAndNameKeyIsRejected() {
    assertThatThrownBy(
            () ->
                update(
                    INSERT_PRODUCT,
                    "00000000-0000-4000-8000-000000000009",
                    "Etude",
                    "TINT",
                    "etude",
                    "tint",
                    "LIP",
                    "LIP_TINT"))
        .isInstanceOf(DuplicateKeyException.class)
        .hasMessageContaining(Product.TYPE_BRAND_NAME_UNIQUE);
  }

  @Test
  void sameShadeKeyInOneProductIsRejectedButAllowedInAnother() {
    update(INSERT_SHADE, TINT_ID, "1호", "1호", null, null, null);

    assertThatThrownBy(() -> update(INSERT_SHADE, TINT_ID, "1호", "1호", null, null, null))
        .isInstanceOf(DuplicateKeyException.class)
        .hasMessageContaining(ProductShade.PRODUCT_NAME_UNIQUE);
    assertThatCode(() -> update(INSERT_SHADE, TONER_ID, "1호", "1호", null, null, null))
        .doesNotThrowAnyException();
  }

  @Test
  void shadeMustReferenceAnExistingProduct() {
    assertThatThrownBy(
            () ->
                update(
                    INSERT_SHADE,
                    "00000000-0000-4000-8000-000000000099",
                    "1호",
                    "1호",
                    null,
                    null,
                    null))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(ProductShade.PRODUCT_FK);
  }

  // --- 색상 ---

  @Test
  void colorWithAllThreeValuesOrNoneIsAccepted() {
    assertThatCode(() -> update(INSERT_SHADE, TINT_ID, "1호", "1호", "#E8452C", "OFFICIAL", false))
        .doesNotThrowAnyException();
    assertThatCode(() -> update(INSERT_SHADE, TINT_ID, "2호", "2호", null, null, null))
        .doesNotThrowAnyException();
  }

  @Test
  void colorWithOnlySomeValuesIsRejected() {
    for (Object[] partial :
        List.of(
            new Object[] {"#E8452C", null, null},
            new Object[] {null, "OFFICIAL", null},
            new Object[] {null, null, false},
            new Object[] {"#E8452C", "OFFICIAL", null},
            new Object[] {"#E8452C", null, true})) {
      assertThatThrownBy(
              () -> update(INSERT_SHADE, TINT_ID, "1호", "1호", partial[0], partial[1], partial[2]))
          .as("hex=%s source=%s estimated=%s", partial)
          .isInstanceOf(DataIntegrityViolationException.class)
          .hasMessageContaining(ProductShade.COLOR_ALL_OR_NONE_CHECK);
    }
  }

  @Test
  void malformedOrLowercaseHexIsRejected() {
    for (String hex : List.of("#e8452c", "E8452C", "#E8452", "#G8452C")) {
      assertThatThrownBy(() -> update(INSERT_SHADE, TINT_ID, "1호", "1호", hex, "OFFICIAL", false))
          .as(hex)
          .isInstanceOf(DataIntegrityViolationException.class)
          .hasMessageContaining(ProductShade.COLOR_HEX_CHECK);
    }
  }

  // --- 수집 출처 식별자 ---

  @Test
  void saleStatusMustBeOneOfTheKnownValues() {
    assertThatCode(() -> setSaleStatus("ON_SALE")).doesNotThrowAnyException();
    assertThatThrownBy(() -> setSaleStatus("ARCHIVED"))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(Product.SALE_STATUS_CHECK);
  }

  @Test
  void sameSourceProductIdInOneSourceIsRejectedButNullSourcesAreNotCompared() {
    update(
        "update products set source = 'OFFICIAL:a.com', source_product_id = '10' where id = ?::uuid",
        TINT_ID);

    assertThatThrownBy(
            () ->
                update(
                    "update products set source = 'OFFICIAL:a.com', source_product_id = '10'"
                        + " where id = ?::uuid",
                    TONER_ID))
        .isInstanceOf(DuplicateKeyException.class)
        .hasMessageContaining(Product.SOURCE_PRODUCT_UNIQUE_INDEX);
    assertThatCode(
            () ->
                update(
                    "update products set source = 'OFFICIAL:b.com', source_product_id = '10'"
                        + " where id = ?::uuid",
                    TONER_ID))
        .doesNotThrowAnyException();
  }

  @Test
  void sameSourceOptionIdInOneProductIsRejectedButNullOptionsAreNotCompared() {
    update(INSERT_SHADE, TINT_ID, "1호", "1호", null, null, null);
    update(INSERT_SHADE, TINT_ID, "2호", "2호", null, null, null);
    update("update product_shades set source_option_id = 'opt-1' where name = '1호'");

    assertThatThrownBy(
            () -> update("update product_shades set source_option_id = 'opt-1' where name = '2호'"))
        .isInstanceOf(DuplicateKeyException.class)
        .hasMessageContaining(ProductShade.SOURCE_OPTION_UNIQUE_INDEX);
    // 옵션 값이 없는 호수는 서로 비교하지 않는다
    assertThatCode(() -> update(INSERT_SHADE, TINT_ID, "3호", "3호", null, null, null))
        .doesNotThrowAnyException();
  }

  @Test
  void optionAliasMustReferenceAnExistingShadeAndBeUniquePerShade() {
    String shadeId = insertShade("1호");
    update(INSERT_ALIAS, shadeId, "old-1");

    assertThatThrownBy(() -> update(INSERT_ALIAS, shadeId, "old-1"))
        .isInstanceOf(DuplicateKeyException.class)
        .hasMessageContaining("product_shade_option_aliases_pkey");
    assertThatThrownBy(() -> update(INSERT_ALIAS, "00000000-0000-4000-8000-000000000099", "old-1"))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(ProductShade.OPTION_ALIAS_FK);
  }

  // --- 색 칸 ---

  @Test
  void shadeColorMustReferenceAnExistingShade() {
    assertThatThrownBy(
            () ->
                update(
                    INSERT_SLOT,
                    "00000000-0000-4000-8000-000000000099",
                    1,
                    null,
                    null,
                    "NONE",
                    null,
                    null,
                    null,
                    null))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(ProductShadeColor.SHADE_FK);
  }

  @Test
  void duplicateSlotOrderInOneShadeIsRejectedWhenTheConstraintIsChecked() {
    String shade = insertShade("1호");
    update(INSERT_SLOT, shade, 1, null, null, "NONE", null, null, null, null);
    // 칸 순서 유니크는 DEFERRABLE INITIALLY DEFERRED 라 문장이 아니라 제약 검사(커밋) 시점에 확인한다
    update(INSERT_SLOT, shade, 1, null, null, "NONE", null, null, null, null);

    assertThatThrownBy(() -> update("set constraints all immediate"))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(ProductShadeColor.SHADE_ORDER_UNIQUE);
  }

  @Test
  void sameSlotOrderIsAllowedInAnotherShade() {
    String first = insertShade("1호");
    String second = insertShade("2호");
    update(INSERT_SLOT, first, 1, null, null, "NONE", null, null, null, null);
    update(INSERT_SLOT, second, 1, null, null, "NONE", null, null, null, null);

    assertThatCode(() -> update("set constraints all immediate")).doesNotThrowAnyException();
  }

  @Test
  void slotOrdersCanBeSwappedInOneTransaction() {
    String shade = insertShade("1호");
    update(INSERT_SLOT, shade, 1, null, null, "NONE", null, null, null, null);
    update(INSERT_SLOT, shade, 2, null, null, "NONE", null, null, null, null);

    // 칸 순서 유니크는 DEFERRABLE 이라 커밋(또는 제약 검사) 시점에 확인한다
    assertThatCode(
            () -> {
              jdbc.update(
                  "update product_shade_colors set sort_order = 3 - sort_order where shade_id = ?::uuid",
                  shade);
              jdbc.execute("set constraints all immediate");
            })
        .doesNotThrowAnyException();
  }

  @Test
  void slotNameAndItsSourceMustAgree() {
    String shade = insertShade("1호");

    assertThatCode(
            () ->
                update(INSERT_SLOT, shade, 1, "Sand", "sand", "SITE_TEXT", null, null, null, null))
        .doesNotThrowAnyException();
    assertThatCode(
            () ->
                update(
                    INSERT_SLOT, shade, 2, "Rose", "rose", "IMAGE_PRINT", null, null, null, null))
        .doesNotThrowAnyException();
    // 이름이 있는데 근거가 NONE
    assertThatThrownBy(
            () -> update(INSERT_SLOT, shade, 3, "Mauve", "mauve", "NONE", null, null, null, null))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(ProductShadeColor.NAME_SOURCE_CHECK);
    // 이름이 없는데 근거가 있음
    assertThatThrownBy(
            () -> update(INSERT_SLOT, shade, 3, null, null, "SITE_TEXT", null, null, null, null))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(ProductShadeColor.NAME_SOURCE_CHECK);
    // 이름과 비교용 키는 함께 있거나 함께 없다
    assertThatThrownBy(
            () -> update(INSERT_SLOT, shade, 3, "Mauve", null, "SITE_TEXT", null, null, null, null))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(ProductShadeColor.NAME_PAIR_CHECK);
    // 순서대로 센 번호 같은 값은 근거가 될 수 없다
    assertThatThrownBy(
            () ->
                update(
                    INSERT_SLOT, shade, 3, "Mauve", "mauve", "MODEL_INDEX", null, null, null, null))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(ProductShadeColor.NAME_SOURCE_CHECK);
  }

  @Test
  void slotColorWithAllFourValuesOrNoneIsAccepted() {
    String shade = insertShade("1호");

    assertThatCode(
            () ->
                update(
                    INSERT_SLOT,
                    shade,
                    1,
                    null,
                    null,
                    "NONE",
                    "#E8452C",
                    "PRODUCT_PHOTO",
                    true,
                    "AUTO_APPROVED"))
        .doesNotThrowAnyException();
    assertThatCode(
            () ->
                update(
                    INSERT_SLOT,
                    shade,
                    2,
                    null,
                    null,
                    "NONE",
                    "#C8102E",
                    "SOURCE_VALUE",
                    true,
                    "BELOW_THRESHOLD"))
        .doesNotThrowAnyException();
    assertThatCode(() -> update(INSERT_SLOT, shade, 3, null, null, "NONE", null, null, null, null))
        .doesNotThrowAnyException();
  }

  @Test
  void slotColorWithOnlySomeValuesIsRejected() {
    String shade = insertShade("1호");
    int order = 1;
    for (Object[] partial :
        List.of(
            new Object[] {"#E8452C", null, null, null},
            new Object[] {null, "WEB_PHOTO", null, null},
            new Object[] {null, null, false, null},
            new Object[] {null, null, null, "AUTO_APPROVED"},
            new Object[] {"#E8452C", "WEB_PHOTO", true, null},
            new Object[] {"#E8452C", "WEB_PHOTO", null, "AUTO_APPROVED"})) {
      int sortOrder = order++;
      assertThatThrownBy(
              () ->
                  update(
                      INSERT_SLOT,
                      shade,
                      sortOrder,
                      null,
                      null,
                      "NONE",
                      partial[0],
                      partial[1],
                      partial[2],
                      partial[3]))
          .as("hex=%s source=%s estimated=%s review=%s", partial)
          .isInstanceOf(DataIntegrityViolationException.class)
          .hasMessageContaining(ProductShadeColor.COLOR_ALL_OR_NONE_CHECK);
    }
  }

  @Test
  void slotHexSourceAndReviewStatusMustBeKnownValues() {
    String shade = insertShade("1호");

    for (String hex : List.of("#e8452c", "E8452C", "#E8452", "#G8452C")) {
      assertThatThrownBy(
              () ->
                  update(
                      INSERT_SLOT,
                      shade,
                      1,
                      null,
                      null,
                      "NONE",
                      hex,
                      "WEB_PHOTO",
                      true,
                      "AUTO_APPROVED"))
          .as(hex)
          .isInstanceOf(DataIntegrityViolationException.class)
          .hasMessageContaining(ProductShadeColor.COLOR_HEX_CHECK);
    }
    assertThatThrownBy(
            () ->
                update(
                    INSERT_SLOT,
                    shade,
                    1,
                    null,
                    null,
                    "NONE",
                    "#E8452C",
                    "OFFICIAL",
                    true,
                    "AUTO_APPROVED"))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(ProductShadeColor.COLOR_SOURCE_CHECK);
    assertThatThrownBy(
            () ->
                update(
                    INSERT_SLOT,
                    shade,
                    1,
                    null,
                    null,
                    "NONE",
                    "#E8452C",
                    "WEB_PHOTO",
                    true,
                    "PENDING"))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(ProductShadeColor.REVIEW_CHECK);
  }

  // --- 앱에서만 지키는 규칙 ---

  @Test
  void shadeOnANonShadeSelectableCategoryIsNotBlockedByTheDatabase() {
    // 호수 선택 불가 규칙은 Product.addShade 에서만 지킨다 (ProductTest). SQL 로 직접 넣으면 DB 는 막지 않는다
    assertThatCode(() -> update(INSERT_SHADE, TONER_ID, "1호", "1호", null, null, null))
        .doesNotThrowAnyException();
  }

  // --- 인덱스 ---

  @Test
  void indexesExistWithTheExpectedNamesAndColumnOrder() {
    assertThat(indexColumns("products"))
        .containsEntry(
            Product.TYPE_BRAND_NAME_UNIQUE,
            List.of("type_code", "brand_normalized", "name_normalized"));
    assertThat(indexColumns("product_shades"))
        .containsEntry(ProductShade.PRODUCT_NAME_UNIQUE, List.of("product_id", "name_normalized"))
        .containsEntry(
            ProductShade.PRODUCT_ORDER_INDEX,
            List.of("product_id", "sort_order", "name_normalized"));
    assertThat(indexColumns("product_shade_colors"))
        .containsEntry(ProductShadeColor.SHADE_ORDER_UNIQUE, List.of("shade_id", "sort_order"))
        .containsEntry(ProductShadeColor.SHADE_ORDER_INDEX, List.of("shade_id", "sort_order"));
    assertThat(indexColumns("products"))
        .containsEntry(Product.SOURCE_PRODUCT_UNIQUE_INDEX, List.of("source", "source_product_id"));
    assertThat(indexColumns("product_shades"))
        .containsEntry(
            ProductShade.SOURCE_OPTION_UNIQUE_INDEX, List.of("product_id", "source_option_id"));
    assertThat(indexColumns("product_types"))
        .containsEntry(ProductType.CATEGORY_ORDER_INDEX, List.of("category_code", "sort_order"))
        .containsEntry(ProductType.CATEGORY_CODE_UNIQUE, List.of("category_code", "code"));
  }

  @Test
  void productsHasNoSeparateCategoryIndex() {
    // 카테고리만으로 제품을 찾는 조회가 없어 만들지 않기로 했다
    assertThat(indexColumns("products").values())
        .noneMatch(columns -> columns.get(0).equals("category_code"));
  }

  /**
   * 세이브포인트 안에서 실행한다. PostgreSQL 은 오류가 난 뒤 같은 트랜잭션의 다음 문장을 모두 거부하므로, 한 테스트에서 여러 위반을 확인하려면 실패한 문장만
   * 되돌려야 한다.
   */
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

  private void setSaleStatus(String status) {
    update("update products set sale_status = ? where id = ?::uuid", status, TINT_ID);
  }

  /** TINT 제품에 호수를 하나 넣고 id 를 돌려준다. */
  private String insertShade(String name) {
    update(INSERT_SHADE, TINT_ID, name, name, null, null, null);
    return jdbc.queryForObject(
        "select id::text from product_shades where product_id = ?::uuid and name = ?",
        String.class,
        TINT_ID,
        name);
  }

  private List<String> constraints(String table) {
    return jdbc.queryForList(
        "select conname from pg_constraint where conrelid = ?::regclass", String.class, table);
  }

  /** 테이블의 인덱스 이름 → 인덱스 컬럼(정의 순서). */
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
