package com.mairor.backend.products;

import static java.util.stream.Collectors.groupingBy;
import static java.util.stream.Collectors.mapping;
import static java.util.stream.Collectors.toList;
import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.products.entity.ProductCategory;
import com.mairor.backend.products.repository.ProductCategoryRepository;
import com.mairor.backend.products.support.CatalogTextNormalizer;
import java.sql.Connection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.jdbc.datasource.init.ScriptUtils;
import org.springframework.transaction.annotation.Transactional;

/**
 * 시드 SQL({@code db/seed/product-categories.sql}, {@code db/seed/dev/product-samples.sql})을 확인한다.
 * 운영과 같은 스키마 SQL 위에 테스트 트랜잭션 안에서 적용하고 끝나면 되돌린다.
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
class ProductSeedSqlTest {

  private static final String CATEGORIES_SEED = "db/seed/product-categories.sql";
  private static final String SAMPLES_SEED = "db/seed/dev/product-samples.sql";

  /** 기능명세 POUCH-004 의 카테고리별 종류 (표시 순서). 시드가 이 표와 같아야 한다. */
  private static final Map<String, List<String>> TYPES_BY_CATEGORY = new LinkedHashMap<>();

  static {
    TYPES_BY_CATEGORY.put(
        "BASE", List.of("CUSHION", "FOUNDATION", "CONCEALER", "SUNSCREEN", "POWDER", "BASE_STICK"));
    TYPES_BY_CATEGORY.put(
        "EYE", List.of("EYESHADOW_PALETTE", "MASCARA", "EYELINER", "FALSE_LASHES"));
    TYPES_BY_CATEGORY.put("BROW", List.of("BROW_PENCIL"));
    TYPES_BY_CATEGORY.put("CHEEK", List.of("BLUSHER", "HIGHLIGHTER", "COMPACT"));
    TYPES_BY_CATEGORY.put(
        "LIP", List.of("LIPSTICK", "LIP_GLOSS", "LIP_TINT", "LIP_BALM", "LIQUID_LIP"));
    TYPES_BY_CATEGORY.put(
        "SKINCARE",
        List.of(
            "TONER",
            "SERUM_AMPOULE",
            "CREAM",
            "CLEANSING_FOAM",
            "CLEANSING_OIL",
            "HAND_EYE_CREAM",
            "MASK_PACK",
            "MIST"));
    TYPES_BY_CATEGORY.put("NAIL", List.of("NAIL_POLISH", "NAIL_FILE"));
    TYPES_BY_CATEGORY.put("FRAGRANCE", List.of("PERFUME"));
    TYPES_BY_CATEGORY.put(
        "TOOL",
        List.of(
            "BRUSH",
            "PUFF",
            "SPONGE",
            "EYELASH_CURLER",
            "HAND_MIRROR",
            "TWEEZERS",
            "COTTON_PAD",
            "COTTON_SWAB"));
  }

  @Autowired private DataSource dataSource;
  @Autowired private JdbcTemplate jdbc;
  @Autowired private ProductCategoryRepository categoryRepository;

  @Test
  void categorySeedHasTheNineCategoriesWithTheirFlags() {
    apply(CATEGORIES_SEED);

    List<Map<String, Object>> rows =
        jdbc.queryForList(
            "select code, matchable, shade_selectable from product_categories order by sort_order");

    assertThat(rows)
        .extracting(r -> r.get("code"))
        .containsExactlyElementsOf(TYPES_BY_CATEGORY.keySet());
    assertThat(rows)
        .filteredOn(r -> (Boolean) r.get("matchable"))
        .extracting(r -> r.get("code"))
        .containsExactly("BASE", "EYE", "BROW", "CHEEK", "LIP");
    assertThat(rows)
        .filteredOn(r -> !(Boolean) r.get("shade_selectable"))
        .extracting(r -> r.get("code"))
        .containsExactly("SKINCARE", "FRAGRANCE", "TOOL");
  }

  @Test
  void categorySeedHasEveryTypeInItsCategoryInDisplayOrder() {
    apply(CATEGORIES_SEED);

    Map<String, List<String>> actual =
        jdbc
            .queryForList(
                "select t.category_code, t.code from product_types t"
                    + " join product_categories c on c.code = t.category_code"
                    + " order by c.sort_order, t.sort_order")
            .stream()
            .collect(
                groupingBy(
                    r -> (String) r.get("category_code"),
                    LinkedHashMap::new,
                    mapping(r -> (String) r.get("code"), toList())));

    assertThat(actual).containsExactlyEntriesOf(TYPES_BY_CATEGORY);
    assertThat(count("product_types")).isEqualTo(38);
  }

  @Test
  void categorySeedLeavesCompatiblePartsEmptyAndAllCategoriesAreStillReturned() {
    apply(CATEGORIES_SEED);

    List<ProductCategory> categories = categoryRepository.findAllByOrderBySortOrderAscCodeAsc();

    assertThat(count("product_category_parts")).isZero();
    assertThat(categories).hasSize(9);
    assertThat(categories).allSatisfy(c -> assertThat(c.getCompatibleParts()).isEmpty());
  }

  @Test
  void categorySeedCanBeAppliedTwiceAndRestoresChangedValues() {
    apply(CATEGORIES_SEED);
    jdbc.update("update product_categories set label = 'x', sort_order = 99 where code = 'LIP'");
    jdbc.update("update product_types set label = 'x', sort_order = 99 where code = 'LIP_TINT'");

    apply(CATEGORIES_SEED);

    assertThat(count("product_categories")).isEqualTo(9);
    assertThat(count("product_types")).isEqualTo(38);
    assertThat(
            jdbc.queryForMap("select label, sort_order from product_categories where code = 'LIP'"))
        .containsEntry("label", "립")
        .containsEntry("sort_order", 5);
    assertThat(
            jdbc.queryForMap("select label, sort_order from product_types where code = 'LIP_TINT'"))
        .containsEntry("label", "립틴트")
        .containsEntry("sort_order", 3);
  }

  @Test
  void sampleSeedCanBeAppliedTwiceAndRestoresChangedValues() {
    apply(CATEGORIES_SEED);
    apply(SAMPLES_SEED);
    jdbc.update(
        "update products set name = 'x', name_normalized = 'x'"
            + " where id = '00000000-0000-4000-8000-000000000101'");
    jdbc.update(
        "update product_shades set sort_order = 99, color_hex = null, color_source = null,"
            + " color_estimated = null where id = '00000000-0000-4000-8000-000000000201'");

    apply(SAMPLES_SEED);

    assertThat(count("products")).isEqualTo(3);
    assertThat(count("product_shades")).isEqualTo(4);
    assertThat(count("product_shade_colors")).isEqualTo(6);
    assertThat(
            jdbc.queryForObject(
                "select name from products where id = '00000000-0000-4000-8000-000000000101'",
                String.class))
        .isEqualTo("Water Gel Tint");
    assertThat(
            jdbc.queryForMap(
                "select sort_order, color_hex from product_shades"
                    + " where id = '00000000-0000-4000-8000-000000000201'"))
        .containsEntry("sort_order", 1)
        .containsEntry("color_hex", "#F2665A");
  }

  @Test
  void sampleSeedHasATintWithThreeShadesAndATonerWithNone() {
    apply(CATEGORIES_SEED);
    apply(SAMPLES_SEED);

    assertThat(
            jdbc.queryForList(
                "select s.name from product_shades s join products p on p.id = s.product_id"
                    + " where p.type_code = 'LIP_TINT' order by s.sort_order, s.name_normalized",
                String.class))
        .containsExactly("01 Coral", "02 Cherry", "03 Nude");
    assertThat(
            jdbc.queryForObject(
                "select count(*) from product_shades s join products p on p.id = s.product_id"
                    + " where p.type_code = 'TONER'",
                Integer.class))
        .isZero();
    assertThat(
            jdbc.queryForObject(
                "select count(*) from product_shades s join products p on p.id = s.product_id"
                    + " where p.type_code = 'LIP_TINT' and s.color_hex is null",
                Integer.class))
        .isEqualTo(1);
  }

  @Test
  void sampleSeedHasAPaletteWithThreeSlotsOfDifferentStates() {
    apply(CATEGORIES_SEED);
    apply(SAMPLES_SEED);

    List<Map<String, Object>> slots =
        jdbc.queryForList(
            "select c.sort_order, c.name, c.name_source, c.color_hex, c.review_status"
                + " from product_shade_colors c join product_shades s on s.id = c.shade_id"
                + " join products p on p.id = s.product_id"
                + " where p.type_code = 'EYESHADOW_PALETTE' order by c.sort_order");

    assertThat(slots).hasSize(3);
    assertThat(slots.get(0))
        .containsEntry("name", "Matte Sand")
        .containsEntry("name_source", "SITE_TEXT")
        .containsEntry("review_status", "AUTO_APPROVED");
    assertThat(slots.get(1))
        .containsEntry("color_hex", "#B76E79")
        .containsEntry("review_status", "BELOW_THRESHOLD");
    assertThat(slots.get(2))
        .containsEntry("name_source", "NONE")
        .containsEntry("color_hex", null)
        .containsEntry("review_status", null);
  }

  @Test
  void everySingleShadeOfTheTintHasOneSlotMatchingItsOldColor() {
    apply(CATEGORIES_SEED);
    apply(SAMPLES_SEED);

    List<Map<String, Object>> rows =
        jdbc.queryForList(
            "select s.name, s.color_hex as shade_hex, c.color_hex as slot_hex, count(*) over"
                + " (partition by s.id) as slots from product_shades s join product_shade_colors c"
                + " on c.shade_id = s.id join products p on p.id = s.product_id"
                + " where p.type_code = 'LIP_TINT' order by s.sort_order");

    assertThat(rows).hasSize(3);
    for (Map<String, Object> r : rows) {
      assertThat(r.get("slots")).as(r.toString()).isEqualTo(1L);
      assertThat(r.get("slot_hex")).as(r.toString()).isEqualTo(r.get("shade_hex"));
    }
  }

  @Test
  void normalizedColumnsInTheSeedsMatchTheNormalizer() {
    apply(CATEGORIES_SEED);
    apply(SAMPLES_SEED);

    List<Map<String, Object>> products =
        jdbc.queryForList("select brand, name, brand_normalized, name_normalized from products");
    List<Map<String, Object>> shades =
        jdbc.queryForList("select name, name_normalized from product_shades");
    List<Map<String, Object>> slots =
        jdbc.queryForList(
            "select name, name_normalized from product_shade_colors where name is not null");

    assertThat(products).isNotEmpty();
    assertThat(shades).isNotEmpty();
    for (Map<String, Object> p : products) {
      assertThat(p.get("brand_normalized"))
          .as("brand %s", p.get("brand"))
          .isEqualTo(CatalogTextNormalizer.normalize((String) p.get("brand")));
      assertThat(p.get("name_normalized"))
          .as("name %s", p.get("name"))
          .isEqualTo(CatalogTextNormalizer.normalize((String) p.get("name")));
    }
    for (Map<String, Object> s : shades) {
      assertThat(s.get("name_normalized"))
          .as("shade %s", s.get("name"))
          .isEqualTo(CatalogTextNormalizer.normalize((String) s.get("name")));
    }
    assertThat(slots).isNotEmpty();
    for (Map<String, Object> c : slots) {
      assertThat(c.get("name_normalized"))
          .as("slot %s", c.get("name"))
          .isEqualTo(CatalogTextNormalizer.normalize((String) c.get("name")));
    }
  }

  /** 테스트 트랜잭션의 연결로 실행해서, 테스트가 끝나면 함께 되돌린다. */
  private void apply(String path) {
    Connection connection = DataSourceUtils.getConnection(dataSource);
    try {
      ScriptUtils.executeSqlScript(connection, new ClassPathResource(path));
    } finally {
      DataSourceUtils.releaseConnection(connection, dataSource);
    }
  }

  private int count(String table) {
    return jdbc.queryForObject("select count(*) from " + table, Integer.class);
  }
}
