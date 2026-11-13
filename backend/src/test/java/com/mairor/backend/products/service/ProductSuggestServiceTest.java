package com.mairor.backend.products.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.products.dto.request.ProductSuggestQuery;
import com.mairor.backend.products.dto.response.ProductSuggestionResponse;
import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.entity.ProductCategory;
import com.mairor.backend.products.entity.ProductType;
import com.mairor.backend.products.repository.ProductNameAliasRepository;
import jakarta.persistence.EntityManager;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.transaction.annotation.Transactional;

/** 제품 후보 검색(자동 완성)의 일치 규칙·정렬·제한. 데이터는 테스트가 직접 만들고 롤백된다. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql,classpath:db/schema/executions.sql",
      "app.security.allowed-origins=http://localhost:3000"
    })
@Transactional
class ProductSuggestServiceTest {

  @Autowired private ProductSuggestService service;
  @Autowired private ProductNameAliasRepository aliases;
  @Autowired private EntityManager em;

  private Product original;
  private Product black;
  private Product gloss;
  private Product cushion;

  @BeforeEach
  void setUp() {
    ProductCategory lip = new ProductCategory("LIP", "립", true, true, 5);
    ProductCategory base = new ProductCategory("BASE", "베이스", true, true, 1);
    em.persist(lip);
    em.persist(base);
    ProductType tintType = new ProductType("LIP_TINT", lip, "립틴트", 1);
    ProductType glossType = new ProductType("LIP_GLOSS", lip, "립글로스", 2);
    ProductType cushionType = new ProductType("CUSHION", base, "쿠션", 1);
    em.persist(tintType);
    em.persist(glossType);
    em.persist(cushionType);
    original = new Product(tintType, "롬앤", "블러 퍼지 틴트 #오리지널");
    original.addShade("01 오리지널", 1, null);
    black = new Product(tintType, "롬앤", "블러 퍼지 틴트 #블랙스펙트럼");
    gloss = new Product(glossType, "롬앤", "글래스팅 퍼지 글로스");
    cushion = new Product(cushionType, "에뛰드", "더블 래스팅 쿠션");
    em.persist(original);
    em.persist(black);
    em.persist(gloss);
    em.persist(cushion);
    em.flush();
    em.clear();
  }

  private static ProductSuggestQuery q(String q) {
    return new ProductSuggestQuery(q, null, null, null);
  }

  private List<String> names(ProductSuggestQuery query) {
    return service.suggest(query).stream().map(ProductSuggestionResponse::name).toList();
  }

  @Test
  void partOfTheNameFindsProductsWithoutShadesToo() {
    assertThat(names(q("퍼지")))
        .containsExactlyInAnyOrder("블러 퍼지 틴트 #오리지널", "블러 퍼지 틴트 #블랙스펙트럼", "글래스팅 퍼지 글로스");
  }

  @Test
  void spacesAndCaseAreIgnoredAndAllWordsMustBePresent() {
    assertThat(names(q("블러퍼지"))).hasSize(2);
    assertThat(names(q("  퍼지   틴트 "))).hasSize(2);
    assertThat(names(q("퍼지 쿠션"))).isEmpty();
  }

  @Test
  void brandIsPartOfTheKey() {
    assertThat(names(q("롬앤 퍼지 글로스"))).containsExactly("글래스팅 퍼지 글로스");
    assertThat(names(q("에뛰드"))).containsExactly("더블 래스팅 쿠션");
  }

  @Test
  void namesStartingWithTheInputComeFirstThenShorterNames() {
    List<String> names = names(q("블러"));
    assertThat(names).containsExactly("블러 퍼지 틴트 #오리지널", "블러 퍼지 틴트 #블랙스펙트럼");
    assertThat(names("퍼지").get(0)).isEqualTo("글래스팅 퍼지 글로스");
  }

  private List<String> names(String text) {
    return names(q(text));
  }

  @Test
  void categoryAndTypeNarrowTheResult() {
    assertThat(names(new ProductSuggestQuery("퍼지", "LIP", "LIP_GLOSS", null)))
        .containsExactly("글래스팅 퍼지 글로스");
    assertThat(names(new ProductSuggestQuery("퍼지", "BASE", null, null))).isEmpty();
    assertThat(names(new ProductSuggestQuery("퍼지", "NOPE", null, null))).isEmpty();
  }

  @Test
  void limitCutsTheList() {
    assertThat(names(new ProductSuggestQuery("퍼지", null, null, 1))).hasSize(1);
  }

  @Test
  void tooShortOrBlankInputGivesNothing() {
    assertThat(names(q("퍼"))).isEmpty();
    assertThat(names(q("   "))).isEmpty();
    assertThat(names(q("롬 "))).isEmpty();
  }

  @Test
  void likeWildcardsAreTakenLiterally() {
    assertThat(names(q("%%"))).isEmpty();
    assertThat(names(q("__"))).isEmpty();
  }

  @Test
  void aliasNamesAreFoundToo() {
    aliases.remember("CUSHION", "에뛰드", "더블웨어 쿠션", cushion.getId(), null, Instant.now());
    assertThat(names(q("더블웨어"))).containsExactly("더블 래스팅 쿠션");
  }

  @Test
  void aProductMatchedByNameAndAliasAppearsOnce() {
    aliases.remember("LIP_TINT", "롬앤", "퍼지틴트", original.getId(), null, Instant.now());
    assertThat(names(q("퍼지 틴트")).stream().filter(n -> n.endsWith("#오리지널")).count()).isEqualTo(1);
  }

  @Test
  void anAliasMustSatisfyEveryWordNotJustTheLongestOne() {
    aliases.remember("CUSHION", "에뛰드", "더블웨어 쿠션", cushion.getId(), null, Instant.now());

    assertThat(names(q("더블웨어 쿠션"))).containsExactly("더블 래스팅 쿠션");
    assertThat(names(q("더블웨어 틴트"))).isEmpty();
    assertThat(names(q("더블웨어 퍼지"))).isEmpty();
  }

  @Test
  void theBestCandidatesSurviveWhenManyProductsMatchTheInput() {
    ProductType tintType = em.find(ProductType.class, "LIP_TINT");
    for (int i = 0; i < 150; i++) {
      em.persist(new Product(tintType, "롬앤", "아주 긴 이름의 인기 상품 번호 " + i + " 틴트 컬렉션"));
    }
    em.persist(new Product(tintType, "롬앤", "틴트 베이스"));
    em.flush();
    em.clear();

    List<String> names = names(new ProductSuggestQuery("틴트", null, null, 3));

    assertThat(names).hasSize(3);
    assertThat(names.get(0)).isEqualTo("틴트 베이스");
  }

  @Test
  void moreWordsThanTheLimitAreIgnoredAfterTheSixth() {
    assertThat(names(q("롬앤 블러 퍼지 틴트 오리지널 롬앤 없는말"))).hasSize(1);
  }
}
