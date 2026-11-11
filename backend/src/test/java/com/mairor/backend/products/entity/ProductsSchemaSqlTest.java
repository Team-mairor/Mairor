package com.mairor.backend.products.entity;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

/**
 * 스키마 SQL({@code db/schema/products.sql})이 카탈로그 엔티티와 맞는지 확인한다.
 *
 * <p>운영과 같은 조건이다. 빈 DB 에 SQL 을 먼저 적용하고 {@code ddl-auto=validate} 로 앱을 띄운다. 엔티티와 SQL 이 어긋나면 앱이 뜨지 않아
 * 실패한다. 설정은 {@code UsersSchemaSqlTest}와 같게 둬서 컨텍스트를 함께 쓴다.
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
class ProductsSchemaSqlTest {

  @Autowired private JdbcTemplate jdbc;

  @Test
  void entitiesValidateAgainstTheSqlSchema() {
    // 앱이 ddl-auto=validate 로 기동했다는 것 자체가 엔티티와 SQL 이 맞다는 뜻이다
    for (String table :
        List.of(
            "product_categories",
            "product_types",
            "product_category_parts",
            "products",
            "product_shades",
            "product_shade_option_aliases",
            "product_shade_colors",
            "catalog_import_runs",
            "catalog_import_items")) {
      assertThat(jdbc.queryForObject("select count(*) from " + table, Integer.class))
          .as(table)
          .isZero();
    }
  }

  @Test
  void productColumnsHaveTheExpectedNullabilityAndLength() {
    List<Map<String, Object>> columns = columns("products");

    assertThat(columns)
        .extracting(c -> c.get("column_name"))
        .containsExactlyInAnyOrder(
            "id",
            "brand",
            "name",
            "brand_normalized",
            "name_normalized",
            "name_compact",
            "category_code",
            "type_code",
            "source",
            "source_product_id",
            "source_url",
            "collected_at",
            "image_url",
            "sale_status",
            "created_at",
            "updated_at");
    for (String optional :
        List.of(
            "source",
            "source_product_id",
            "source_url",
            "collected_at",
            "image_url",
            "sale_status")) {
      assertThat(column(columns, optional).get("is_nullable")).as(optional).isEqualTo("YES");
    }
    assertThat(column(columns, "brand").get("character_maximum_length"))
        .isEqualTo(Product.BRAND_MAX_LENGTH);
    assertThat(column(columns, "name").get("character_maximum_length"))
        .isEqualTo(Product.NAME_MAX_LENGTH);
    assertThat(column(columns, "brand_normalized").get("character_maximum_length"))
        .isEqualTo(Product.BRAND_MAX_LENGTH * 2);
    assertThat(column(columns, "name_normalized").get("character_maximum_length"))
        .isEqualTo(Product.NAME_MAX_LENGTH * 2);
    assertThat(column(columns, "image_url").get("character_maximum_length"))
        .isEqualTo(Product.IMAGE_URL_MAX_LENGTH);
    // OFFICIAL:<도메인> 꼴이라 도메인이 길면 30자를 넘는다
    assertThat(column(columns, "source").get("character_maximum_length"))
        .isEqualTo(Product.SOURCE_MAX_LENGTH);
    assertThat(column(columns, "source_product_id").get("character_maximum_length"))
        .isEqualTo(Product.SOURCE_PRODUCT_ID_MAX_LENGTH);
    assertThat(column(columns, "source_url").get("character_maximum_length"))
        .isEqualTo(Product.SOURCE_URL_MAX_LENGTH);
  }

  @Test
  void shadeColumnsHaveTheExpectedNullabilityAndLength() {
    List<Map<String, Object>> columns = columns("product_shades");

    assertThat(columns)
        .extracting(c -> c.get("column_name"))
        .containsExactlyInAnyOrder(
            "id",
            "product_id",
            "name",
            "name_normalized",
            "sort_order",
            "color_hex",
            "color_source",
            "color_estimated",
            "source_option_id",
            "created_at",
            "updated_at");
    for (String color :
        List.of("color_hex", "color_source", "color_estimated", "source_option_id")) {
      assertThat(column(columns, color).get("is_nullable")).as(color).isEqualTo("YES");
    }
    assertThat(column(columns, "name").get("character_maximum_length"))
        .isEqualTo(ProductShade.NAME_MAX_LENGTH);
    assertThat(column(columns, "name_normalized").get("character_maximum_length"))
        .isEqualTo(ProductShade.NAME_MAX_LENGTH * 2);
    assertThat(column(columns, "color_hex").get("character_maximum_length")).isEqualTo(7);
    assertThat(column(columns, "source_option_id").get("character_maximum_length"))
        .isEqualTo(ProductShade.SOURCE_OPTION_MAX_LENGTH);
  }

  @Test
  void shadeColorColumnsHaveTheExpectedNullabilityAndLength() {
    List<Map<String, Object>> columns = columns("product_shade_colors");

    assertThat(columns)
        .extracting(c -> c.get("column_name"))
        .containsExactlyInAnyOrder(
            "id",
            "shade_id",
            "sort_order",
            "name",
            "name_normalized",
            "name_source",
            "color_hex",
            "color_source",
            "color_estimated",
            "review_status",
            "source_collected_at",
            "source_item_id",
            "source_evidence_key",
            "created_at",
            "updated_at");
    for (String optional :
        List.of(
            "name",
            "name_normalized",
            "color_hex",
            "color_source",
            "color_estimated",
            "review_status",
            "source_collected_at",
            "source_item_id",
            "source_evidence_key")) {
      assertThat(column(columns, optional).get("is_nullable")).as(optional).isEqualTo("YES");
    }
    for (String required : List.of("shade_id", "sort_order", "name_source")) {
      assertThat(column(columns, required).get("is_nullable")).as(required).isEqualTo("NO");
    }
    assertThat(column(columns, "name").get("character_maximum_length"))
        .isEqualTo(ProductShadeColor.NAME_MAX_LENGTH);
    assertThat(column(columns, "name_normalized").get("character_maximum_length"))
        .isEqualTo(ProductShadeColor.NAME_MAX_LENGTH * 2);
    assertThat(column(columns, "color_hex").get("character_maximum_length")).isEqualTo(7);
    assertThat(column(columns, "source_evidence_key").get("character_maximum_length"))
        .isEqualTo(ProductShadeColor.EVIDENCE_KEY_MAX_LENGTH);
  }

  @Test
  void importRunColumnsHaveTheExpectedNullabilityAndLength() {
    List<Map<String, Object>> columns = columns("catalog_import_runs");

    assertThat(columns)
        .extracting(c -> c.get("column_name"))
        .containsExactlyInAnyOrder(
            "id",
            "run_id",
            "seed",
            "collector_version",
            "result_file",
            "status",
            "collector_started_at",
            "last_heartbeat_at",
            "finished_at",
            "created_at",
            "updated_at");
    for (String optional :
        List.of(
            "seed", "collector_version", "result_file", "collector_started_at", "finished_at")) {
      assertThat(column(columns, optional).get("is_nullable")).as(optional).isEqualTo("YES");
    }
    for (String required : List.of("run_id", "status", "last_heartbeat_at")) {
      assertThat(column(columns, required).get("is_nullable")).as(required).isEqualTo("NO");
    }
    assertThat(column(columns, "run_id").get("character_maximum_length"))
        .isEqualTo(CatalogImportRun.RUN_ID_MAX_LENGTH);
    assertThat(column(columns, "seed").get("character_maximum_length"))
        .isEqualTo(CatalogImportRun.SEED_MAX_LENGTH);
    assertThat(column(columns, "collector_version").get("character_maximum_length"))
        .isEqualTo(CatalogImportRun.COLLECTOR_VERSION_MAX_LENGTH);
    assertThat(column(columns, "result_file").get("character_maximum_length"))
        .isEqualTo(CatalogImportRun.RESULT_FILE_MAX_LENGTH);
  }

  @Test
  void importItemColumnsHaveTheExpectedNullabilityAndLength() {
    List<Map<String, Object>> columns = columns("catalog_import_items");

    assertThat(columns)
        .extracting(c -> c.get("column_name"))
        .containsExactlyInAnyOrder(
            "id",
            "run_id",
            "item_key",
            "source",
            "source_product_id",
            "outcome",
            "partial",
            "reasons",
            "product_id",
            "colors_applied",
            "message",
            "created_at",
            "updated_at");
    for (String optional : List.of("source", "source_product_id", "product_id", "message")) {
      assertThat(column(columns, optional).get("is_nullable")).as(optional).isEqualTo("YES");
    }
    for (String required :
        List.of("run_id", "item_key", "outcome", "partial", "reasons", "colors_applied")) {
      assertThat(column(columns, required).get("is_nullable")).as(required).isEqualTo("NO");
    }
    assertThat(column(columns, "item_key").get("character_maximum_length"))
        .isEqualTo(CatalogImportItem.ITEM_KEY_MAX_LENGTH);
    assertThat(column(columns, "source").get("character_maximum_length"))
        .isEqualTo(CatalogImportItem.SOURCE_MAX_LENGTH);
    assertThat(column(columns, "source_product_id").get("character_maximum_length"))
        .isEqualTo(CatalogImportItem.SOURCE_PRODUCT_ID_MAX_LENGTH);
    assertThat(column(columns, "reasons").get("character_maximum_length"))
        .isEqualTo(CatalogImportItem.REASONS_MAX_LENGTH);
    assertThat(column(columns, "message").get("character_maximum_length"))
        .isEqualTo(CatalogImportItem.MESSAGE_MAX_LENGTH);
  }

  private List<Map<String, Object>> columns(String table) {
    return jdbc.queryForList(
        "select column_name, is_nullable, character_maximum_length "
            + "from information_schema.columns where table_name = ?",
        table);
  }

  private static Map<String, Object> column(List<Map<String, Object>> columns, String name) {
    return columns.stream()
        .filter(c -> name.equals(c.get("column_name")))
        .findFirst()
        .orElseThrow();
  }
}
