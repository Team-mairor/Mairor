package com.mairor.backend.products.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.catchThrowableOfType;
import static org.assertj.core.api.Assertions.tuple;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.products.dto.request.ProductSearchQuery;
import com.mairor.backend.products.dto.response.ColorInfoResponse;
import com.mairor.backend.products.dto.response.ProductResponse;
import com.mairor.backend.products.dto.response.ShadeResponse;
import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.entity.ProductCategory;
import com.mairor.backend.products.entity.ProductType;
import com.mairor.backend.products.entity.ShadeColor;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import java.util.List;
import java.util.UUID;
import java.util.function.Consumer;
import java.util.function.Supplier;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.transaction.annotation.Transactional;

/**
 * 제품 검색·상세 조회 서비스. 형식 검사({@code @CatalogText} 등)는 컨트롤러 단계라 여기서는 형식이 맞는 쿼리만 넣는다. 데이터는 테스트가 직접 만들고
 * 롤백된다 (설정은 {@code ProductRepositoriesTest} 와 같게 둬서 컨텍스트를 함께 쓴다).
 *
 * <p>모든 테스트는 setUp 의 flush·clear 뒤 비어 있는 영속성 컨텍스트에서 시작한다. 쿼리 수 테스트는 경우마다 메서드를 나눠 새 상태에서 잰다.
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
class ProductSearchServiceTest {

  private static final String NBSP = Character.toString(0x00A0);
  private static final String BRAND = "Mairor Sample";
  private static final String NAME = "Water Gel Tint";

  /** 엔티티 상한(200)을 앞뒤 공백까지 꽉 채운 제품명. 앞뒤 공백을 지우면 198자다. */
  private static final String LONG_NAME = " " + "x".repeat(Product.NAME_MAX_LENGTH - 2) + " ";

  @Autowired private ProductSearchService service;
  @Autowired private EntityManager em;
  @Autowired private EntityManagerFactory emf;

  private Product tint;

  @BeforeEach
  void setUp() {
    ProductCategory lip = new ProductCategory("LIP", "립", true, true, 5);
    ProductCategory base = new ProductCategory("BASE", "베이스", true, true, 1);
    ProductCategory skincare = new ProductCategory("SKINCARE", "스킨케어", false, false, 6);
    em.persist(lip);
    em.persist(base);
    em.persist(skincare);
    ProductType lipTint = new ProductType("LIP_TINT", lip, "립틴트", 1);
    ProductType cushion = new ProductType("CUSHION", base, "쿠션", 1);
    ProductType toner = new ProductType("TONER", skincare, "토너", 1);
    em.persist(lipTint);
    em.persist(cushion);
    em.persist(toner);

    // 호수 순서: 00 Base(0) → 01 Coral(1) → 02 Cherry(1). 같은 순서 값이면 이름 순. 넣는 순서는 다르게 한다
    tint = new Product(lipTint, BRAND, NAME);
    tint.addShade("02 Cherry", 1, ShadeColor.of("#c8102e", "SAMPLE", true));
    tint.addShade("00 Base", 0, null);
    tint.addShade("01 Coral", 1, ShadeColor.of("#F2665A", "SAMPLE", false));
    em.persist(tint);

    // 같은 브랜드·제품명이지만 다른 종류
    em.persist(new Product(cushion, BRAND, NAME));
    // 호수가 없는 카테고리의 제품
    em.persist(new Product(toner, BRAND, "Daily Toner"));
    // 엔티티 상한까지 채운 이름
    em.persist(new Product(lipTint, BRAND, LONG_NAME));

    em.flush();
    em.clear();
  }

  private static ProductSearchQuery query(String category, String type, String brand, String name) {
    return new ProductSearchQuery(category, type, brand, name);
  }

  private List<ProductResponse> searchTint(String brand, String name) {
    return service.search(query("LIP", "LIP_TINT", brand, name));
  }

  @Test
  void exactMatchReturnsTheProductAsStoredInTheCatalog() {
    List<ProductResponse> items = searchTint(BRAND, NAME);

    assertThat(items).hasSize(1);
    ProductResponse item = items.get(0);
    assertThat(item.productId()).isEqualTo(tint.getId().toString());
    assertThat(item.brand()).isEqualTo(BRAND);
    assertThat(item.name()).isEqualTo(NAME);
    assertThat(item.category()).isEqualTo("LIP");
    assertThat(item.type()).isEqualTo("LIP_TINT");
  }

  @Test
  void caseAndWhitespaceDifferencesStillMatchAndTheCatalogOriginalIsReturned() {
    List<ProductResponse> items =
        searchTint("  mairor" + NBSP + "SAMPLE ", "WATER   gel" + NBSP + "tint");

    assertThat(items)
        .extracting(ProductResponse::brand, ProductResponse::name)
        .containsExactly(tuple(BRAND, NAME));
  }

  @Test
  void nothingMatchesUnlessTypeBrandAndNameAreAllTheSame() {
    assertThat(searchTint(BRAND, "Other Tint")).isEmpty();
    assertThat(searchTint("Other Brand", NAME)).isEmpty();
    // 같은 브랜드·제품명이 CUSHION 에도 있지만 종류별로 자기 제품만 나온다
    assertThat(searchTint(BRAND, NAME))
        .extracting(ProductResponse::type)
        .containsExactly("LIP_TINT");
    assertThat(service.search(query("BASE", "CUSHION", BRAND, NAME)))
        .extracting(ProductResponse::type)
        .containsExactly("CUSHION");
    // 토너의 이름으로 다른 종류를 찾으면 없다
    assertThat(service.search(query("BASE", "CUSHION", BRAND, "Daily Toner"))).isEmpty();
  }

  @Test
  void shadesComeInSortOrderThenName() {
    assertThat(searchTint(BRAND, NAME).get(0).shades())
        .extracting(ShadeResponse::name)
        .containsExactly("00 Base", "01 Coral", "02 Cherry");
  }

  @Test
  void shadeColorIsSrgbUppercaseHexWithCatalogSourceOrNull() {
    List<ShadeResponse> shades = searchTint(BRAND, NAME).get(0).shades();

    assertThat(shades.get(0).color()).isNull();
    assertThat(shades.get(1).color())
        .isEqualTo(new ColorInfoResponse("sRGB", "#F2665A", "CATALOG", false));
    // 내부 출처가 SAMPLE 이어도 CATALOG 로, 소문자로 넣은 HEX 는 대문자로 나온다
    assertThat(shades.get(2).color())
        .isEqualTo(new ColorInfoResponse("sRGB", "#C8102E", "CATALOG", true));
    assertThat(shades).allSatisfy(s -> assertThat(s.shadeId()).isNotBlank());
  }

  @Test
  void productWithoutShadesHasAnEmptyList() {
    List<ProductResponse> items = service.search(query("SKINCARE", "TONER", BRAND, "Daily Toner"));

    assertThat(items).hasSize(1);
    assertThat(items.get(0).shades()).isNotNull().isEmpty();
  }

  @Test
  void productStoredAtTheEntityLimitIsFoundByItsTrimmedName() {
    assertThat(searchTint(BRAND, LONG_NAME.strip())).hasSize(1);
    assertThat(searchTint(BRAND, LONG_NAME)).hasSize(1);
  }

  private static ErrorResponse.FieldError invalidField(Runnable call) {
    BusinessException e = catchThrowableOfType(BusinessException.class, call::run);
    assertThat(e).isNotNull();
    assertThat(e.code()).isEqualTo("VALIDATION_FAILED");
    assertThat(e.status().value()).isEqualTo(400);
    assertThat(e.details()).hasSize(1);
    return e.details().get(0);
  }

  @Test
  void typeOfAnotherCategoryIsATypeError() {
    assertThat(invalidField(() -> service.search(query("LIP", "CUSHION", BRAND, NAME))).field())
        .isEqualTo("type");
  }

  @Test
  void unknownTypeInAKnownCategoryIsATypeError() {
    assertThat(invalidField(() -> service.search(query("LIP", "UNKNOWN", BRAND, NAME))).field())
        .isEqualTo("type");
  }

  @Test
  void unknownCategoryIsACategoryErrorEvenWhenTheTypeExists() {
    assertThat(
            invalidField(() -> service.search(query("UNKNOWN", "LIP_TINT", BRAND, NAME))).field())
        .isEqualTo("category");
  }

  @Test
  void unknownCategoryAndTypeIsACategoryError() {
    assertThat(invalidField(() -> service.search(query("UNKNOWN", "UNKNOWN", BRAND, NAME))).field())
        .isEqualTo("category");
  }

  @Test
  void getReturnsTheSameShapeAsASearchItem() {
    assertThat(service.get(tint.getId())).isEqualTo(searchTint(BRAND, NAME).get(0));
  }

  @Test
  void getOfAnUnknownIdIsNotFound() {
    assertThatThrownBy(() -> service.get(UUID.randomUUID()))
        .isInstanceOfSatisfying(
            BusinessException.class, e -> assertThat(e.code()).isEqualTo("NOT_FOUND"));
  }

  /** 통계를 초기화하고 호출한 뒤, 응답 필드를 검증(LAZY 연관이 실제로 쓰이게)하고 쿼리 수를 돌려준다. 통계는 이 안에서만 켰다가 되돌린다. */
  private <T> long countQueries(Supplier<T> call, Consumer<T> verify) {
    Statistics statistics = emf.unwrap(SessionFactory.class).getStatistics();
    boolean wasEnabled = statistics.isStatisticsEnabled();
    statistics.setStatisticsEnabled(true);
    try {
      statistics.clear();
      T result = call.get();
      verify.accept(result);
      return statistics.getPrepareStatementCount();
    } finally {
      statistics.setStatisticsEnabled(wasEnabled);
    }
  }

  @Test
  void searchWithAMatchRunsThreeQueries() {
    long queries =
        countQueries(
            () -> searchTint(BRAND, NAME),
            items -> {
              assertThat(items.get(0).category()).isEqualTo("LIP");
              assertThat(items.get(0).type()).isEqualTo("LIP_TINT");
              assertThat(items.get(0).shades()).hasSize(3);
            });

    assertThat(queries).isEqualTo(3);
  }

  @Test
  void searchWithoutAMatchRunsTwoQueries() {
    long queries =
        countQueries(() -> searchTint(BRAND, "Other Tint"), items -> assertThat(items).isEmpty());

    assertThat(queries).isEqualTo(2);
  }

  @Test
  void getRunsTwoQueriesWithoutLoadingCategoryOrType() {
    long queries =
        countQueries(
            () -> service.get(tint.getId()),
            item -> {
              assertThat(item.category()).isEqualTo("LIP");
              assertThat(item.type()).isEqualTo("LIP_TINT");
              assertThat(item.shades()).hasSize(3);
            });

    assertThat(queries).isEqualTo(2);
  }
}
