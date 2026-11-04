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
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql",
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
