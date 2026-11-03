package com.mairor.backend.products.repository;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.entity.ProductCategory;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductType;
import com.mairor.backend.products.entity.ShadeColor;
import jakarta.persistence.EntityManager;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

/**
 * 카탈로그 리포지토리의 조회 조건과 정렬을 확인한다. 운영과 같은 스키마 SQL 위에서 돌린다 (설정은 {@code ProductsSchemaSqlTest}와 같게 둬서
 * 컨텍스트를 함께 쓴다).
 *
 * <p>정렬은 넣는 순서와 기대 순서를 일부러 다르게 해서, 결과가 저장 순서가 아니라 ORDER BY 조건을 따르는지 본다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql",
      "app.security.allowed-origins=http://localhost:3000"
    })
@Transactional
class ProductRepositoriesTest {

  @Autowired private EntityManager em;
  @Autowired private JdbcTemplate jdbc;
  @Autowired private ProductCategoryRepository categoryRepository;
  @Autowired private ProductTypeRepository typeRepository;
  @Autowired private ProductRepository productRepository;
  @Autowired private ProductShadeRepository shadeRepository;

  private ProductCategory lip;
  private ProductType lipTint;
  private ProductType lipstick;

  @BeforeEach
  void setUp() {
    // 표시 순서: BASE(1) → LIP(5) → SKINCARE(6). 넣는 순서는 다르게 한다
    ProductCategory skincare = new ProductCategory("SKINCARE", "스킨케어", false, false, 6);
    lip = new ProductCategory("LIP", "립", true, true, 5);
    ProductCategory base = new ProductCategory("BASE", "베이스", true, true, 1);
    em.persist(skincare);
    em.persist(lip);
    em.persist(base);

    // LIP 안: LIPSTICK(1) → LIP_GLOSS(2) → LIP_TINT(2). 같은 순서 값이면 코드 순이다
    lipTint = new ProductType("LIP_TINT", lip, "립틴트", 2);
    ProductType lipGloss = new ProductType("LIP_GLOSS", lip, "립글로스", 2);
    lipstick = new ProductType("LIPSTICK", lip, "립스틱", 1);
    em.persist(lipTint);
    em.persist(lipGloss);
    em.persist(lipstick);
    em.persist(new ProductType("TONER", skincare, "토너", 1));
    em.persist(new ProductType("CUSHION", base, "쿠션", 1));
    em.flush();
  }

  @Test
  void categoriesComeInDisplayOrderWithEmptyCompatibleParts() {
    em.clear();

    List<ProductCategory> categories = categoryRepository.findAllByOrderBySortOrderAscCodeAsc();

    assertThat(categories)
        .extracting(ProductCategory::getCode)
        .containsExactly("BASE", "LIP", "SKINCARE");
    assertThat(categories).allSatisfy(c -> assertThat(c.getCompatibleParts()).isEmpty());
  }

  @Test
  void categoriesWithAndWithoutCompatiblePartsAreAllReturned() {
    // 호환 부위 값은 아직 시드하지 않지만, 일부 카테고리에만 있어도 나머지가 빠지지 않는지 확인한다
    jdbc.update(
        "insert into product_category_parts (category_code, part_code) values ('LIP', 'P1')");
    em.clear();

    List<ProductCategory> categories = categoryRepository.findAllByOrderBySortOrderAscCodeAsc();

    assertThat(categories)
        .extracting(ProductCategory::getCode)
        .containsExactly("BASE", "LIP", "SKINCARE");
    assertThat(categories.get(1).getCompatibleParts()).containsExactly("P1");
    assertThat(categories.get(0).getCompatibleParts()).isEmpty();
  }

  @Test
  void typesOfACategoryComeInSortOrderThenCode() {
    em.clear();

    assertThat(typeRepository.findByCategoryCodeOrderBySortOrderAscCodeAsc("LIP"))
        .extracting(ProductType::getCode)
        .containsExactly("LIPSTICK", "LIP_GLOSS", "LIP_TINT");
  }

  @Test
  void allTypesComeGroupedByCategoryDisplayOrder() {
    em.clear();

    assertThat(typeRepository.findAllInDisplayOrder())
        .extracting(ProductType::getCode)
        .containsExactly("CUSHION", "LIPSTICK", "LIP_GLOSS", "LIP_TINT", "TONER");
  }

  @Test
  void exactSearchIgnoresCaseAndWhitespaceDifferences() {
    Product saved = productRepository.saveAndFlush(new Product(lipTint, "ETUDE", "Dear Darling"));
    em.clear();

    assertThat(productRepository.findExact("LIP_TINT", "  etude ", "dear   DARLING"))
        .get()
        .extracting(Product::getId)
        .isEqualTo(saved.getId());
  }

  @Test
  void exactSearchDoesNotMatchAnotherTypeOrAPartialName() {
    productRepository.saveAndFlush(new Product(lipTint, "ETUDE", "Dear Darling"));
    em.clear();

    assertThat(productRepository.findExact("LIPSTICK", "ETUDE", "Dear Darling")).isEmpty();
    assertThat(productRepository.findExact("LIP_TINT", "ETUDE", "Dear")).isEmpty();
  }

  @Test
  void sameProductWithDifferentFormattingCannotBeSavedTwice() {
    productRepository.saveAndFlush(new Product(lipTint, "ETUDE", "Dear Darling"));

    assertThatThrownBy(
            () -> productRepository.saveAndFlush(new Product(lipTint, " etude", "DEAR  darling")))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(Product.TYPE_BRAND_NAME_UNIQUE);
  }

  @Test
  void sameBrandAndNameIsAllowedForADifferentType() {
    productRepository.saveAndFlush(new Product(lipTint, "ETUDE", "Dear Darling"));

    assertThat(productRepository.saveAndFlush(new Product(lipstick, "ETUDE", "Dear Darling")))
        .extracting(Product::getId)
        .isNotNull();
  }

  @Test
  void shadesComeInSortOrderThenNormalizedNameNotInInsertionOrder() {
    Product product = new Product(lipTint, "ETUDE", "Dear Darling");
    // 넣는 순서: (2, b) → (1, C) → (1, a). 기대 순서: (1, a) → (1, C) → (2, b)
    product.addShade("b", 2, null);
    product.addShade("C", 1, ShadeColor.of("#c8102e", "OFFICIAL", false));
    product.addShade("a", 1, null);
    UUID id = productRepository.saveAndFlush(product).getId();
    em.clear();

    assertThat(shadeRepository.findByProductIdOrderBySortOrderAscNameNormalizedAsc(id))
        .extracting(ProductShade::getName)
        .containsExactly("a", "C", "b");
    // 제품에서 읽는 호수 목록도 같은 순서다
    assertThat(productRepository.findById(id).orElseThrow().getShades())
        .extracting(ProductShade::getName)
        .containsExactly("a", "C", "b");
  }

  @Test
  void shadeColorIsStoredAndReadBackOrStaysNull() {
    Product product = new Product(lipTint, "ETUDE", "Dear Darling");
    product.addShade("1호", 1, ShadeColor.of("#e8452c", "OFFICIAL", true));
    product.addShade("2호", 2, null);
    UUID id = productRepository.saveAndFlush(product).getId();
    em.clear();

    List<ProductShade> shades =
        shadeRepository.findByProductIdOrderBySortOrderAscNameNormalizedAsc(id);

    assertThat(shades.get(0).getColor()).isEqualTo(ShadeColor.of("#E8452C", "OFFICIAL", true));
    assertThat(shades.get(1).getColor()).isNull();
    assertThat(
            jdbc.queryForMap(
                "select color_hex, color_source, color_estimated from product_shades where name = '2호'"))
        .allSatisfy((column, value) -> assertThat(value).as(column).isNull());
  }

  @Test
  void productCategoryAndTypeAreStoredTogether() {
    UUID id = productRepository.saveAndFlush(new Product(lipTint, "ETUDE", "Dear Darling")).getId();

    assertThat(jdbc.queryForMap("select category_code, type_code from products where id = ?", id))
        .containsEntry("category_code", "LIP")
        .containsEntry("type_code", "LIP_TINT");
  }
}
