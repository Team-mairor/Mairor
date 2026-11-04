package com.mairor.backend.products.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.tuple;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.products.dto.response.ProductCategoryResponse;
import com.mairor.backend.products.dto.response.ProductTypeResponse;
import com.mairor.backend.products.entity.ProductCategory;
import com.mairor.backend.products.entity.ProductType;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import java.util.List;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

/**
 * 카테고리·종류 목록 서비스가 리포지토리 결과를 응답으로 묶는 방식을 확인한다. 시드 값 자체는 {@code ProductSeedSqlTest} 가 검증하므로 여기서는 데이터를
 * 직접 만든다. 운영과 같은 스키마 SQL 위에서 돌리고(설정은 {@code ProductRepositoriesTest} 와 같게 둬서 컨텍스트를 함께 쓴다), 테스트가 끝나면
 * 롤백된다.
 *
 * <p>정렬은 넣는 순서와 기대 순서를 일부러 다르게 해서, 결과가 저장 순서가 아니라 정렬 조건을 따르는지 본다.
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
class ProductCategoryServiceTest {

  @Autowired private ProductCategoryService service;
  @Autowired private EntityManager em;
  @Autowired private EntityManagerFactory emf;
  @Autowired private JdbcTemplate jdbc;

  @BeforeEach
  void setUp() {
    // 표시 순서: AAA(1) → BBB(1) → CCC(2) → DDD(3). 같은 순서 값이면 코드 순이다. 플래그 조합은 넷 다 다르다
    ProductCategory ddd = new ProductCategory("DDD", "디", false, false, 3);
    ProductCategory ccc = new ProductCategory("CCC", "씨", false, true, 2);
    ProductCategory bbb = new ProductCategory("BBB", "비", true, true, 1);
    ProductCategory aaa = new ProductCategory("AAA", "에이", true, false, 1);
    em.persist(ddd);
    em.persist(ccc);
    em.persist(bbb);
    em.persist(aaa);

    // 카테고리를 섞어서 넣는다. AAA 안: A_ONE_A(1) → A_ONE_B(1) → A_TWO(2). DDD 에는 종류가 없다
    em.persist(new ProductType("C_TWO", ccc, "씨 둘", 2));
    em.persist(new ProductType("A_TWO", aaa, "에이 둘", 2));
    em.persist(new ProductType("B_TWO", bbb, "비 둘", 2));
    em.persist(new ProductType("A_ONE_B", aaa, "에이 하나 비", 1));
    em.persist(new ProductType("C_ONE", ccc, "씨 하나", 1));
    em.persist(new ProductType("B_ONE", bbb, "비 하나", 1));
    em.persist(new ProductType("A_ONE_A", aaa, "에이 하나 에이", 1));
    em.flush();

    // 호환 부위: AAA 에 셋(순서 섞어서), CCC 에 하나. BBB·DDD 에는 없다
    jdbc.update(
        "insert into product_category_parts (category_code, part_code) values"
            + " ('AAA', 'P3'), ('AAA', 'P1'), ('CCC', 'P9'), ('AAA', 'P2')");
    em.clear();
  }

  @Test
  void categoriesComeInSortOrderThenCode() {
    assertThat(service.list())
        .extracting(ProductCategoryResponse::code)
        .containsExactly("AAA", "BBB", "CCC", "DDD");
  }

  @Test
  void labelAndFlagsAreCopiedAsTheyAre() {
    assertThat(service.list())
        .extracting(
            ProductCategoryResponse::code,
            ProductCategoryResponse::label,
            ProductCategoryResponse::matchable,
            ProductCategoryResponse::shadeSelectable)
        .containsExactly(
            tuple("AAA", "에이", true, false),
            tuple("BBB", "비", true, true),
            tuple("CCC", "씨", false, true),
            tuple("DDD", "디", false, false));
  }

  @Test
  void typesAreGroupedIntoTheirCategoryInSortOrderThenCode() {
    List<ProductCategoryResponse> categories = service.list();

    assertThat(categories.get(0).types())
        .containsExactly(
            new ProductTypeResponse("A_ONE_A", "에이 하나 에이"),
            new ProductTypeResponse("A_ONE_B", "에이 하나 비"),
            new ProductTypeResponse("A_TWO", "에이 둘"));
    assertThat(categories.get(1).types())
        .extracting(ProductTypeResponse::code)
        .containsExactly("B_ONE", "B_TWO");
    assertThat(categories.get(2).types())
        .extracting(ProductTypeResponse::code)
        .containsExactly("C_ONE", "C_TWO");
  }

  @Test
  void categoryWithoutTypesIsIncludedWithAnEmptyList() {
    ProductCategoryResponse ddd = service.list().get(3);

    assertThat(ddd.code()).isEqualTo("DDD");
    assertThat(ddd.types()).isNotNull().isEmpty();
  }

  @Test
  void compatiblePartsAreSortedAndCategoriesAreNotDuplicated() {
    List<ProductCategoryResponse> categories = service.list();

    assertThat(categories).hasSize(4);
    assertThat(categories.get(0).compatibleParts()).containsExactly("P1", "P2", "P3");
    assertThat(categories.get(1).compatibleParts()).isNotNull().isEmpty();
    assertThat(categories.get(2).compatibleParts()).containsExactly("P9");
    assertThat(categories.get(3).compatibleParts()).isNotNull().isEmpty();
  }

  @Test
  void listRunsTwoQueriesWithoutNPlusOne() {
    Statistics statistics = emf.unwrap(SessionFactory.class).getStatistics();
    boolean wasEnabled = statistics.isStatisticsEnabled();
    statistics.setStatisticsEnabled(true);
    try {
      statistics.clear();

      service.list();

      assertThat(statistics.getPrepareStatementCount()).isEqualTo(2);
    } finally {
      statistics.setStatisticsEnabled(wasEnabled);
    }
  }
}
