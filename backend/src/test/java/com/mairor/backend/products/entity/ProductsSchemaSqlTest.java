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
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql",
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
            "product_shades")) {
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
            "category_code",
            "type_code",
            "source",
            "source_product_id",
            "source_url",
            "collected_at",
            "created_at",
            "updated_at");
    for (String optional : List.of("source", "source_product_id", "source_url", "collected_at")) {
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
            "created_at",
            "updated_at");
    for (String color : List.of("color_hex", "color_source", "color_estimated")) {
      assertThat(column(columns, color).get("is_nullable")).as(color).isEqualTo("YES");
    }
    assertThat(column(columns, "name").get("character_maximum_length"))
        .isEqualTo(ProductShade.NAME_MAX_LENGTH);
    assertThat(column(columns, "name_normalized").get("character_maximum_length"))
        .isEqualTo(ProductShade.NAME_MAX_LENGTH * 2);
    assertThat(column(columns, "color_hex").get("character_maximum_length")).isEqualTo(7);
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
