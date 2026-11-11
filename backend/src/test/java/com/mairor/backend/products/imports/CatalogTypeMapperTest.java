package com.mairor.backend.products.imports;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.products.entity.ProductCategory;
import com.mairor.backend.products.entity.ProductType;
import com.mairor.backend.products.imports.TypeResolution.Origin;
import com.mairor.backend.products.repository.ProductTypeRepository;
import jakarta.persistence.EntityManager;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.ObjectMapper;

/** 매핑표와 힌트로 카테고리·종류를 정하는 순서. 종류 존재와 카테고리 소속은 DB 기준이다. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql,classpath:db/schema/executions.sql",
      "app.security.allowed-origins=http://localhost:3000"
    })
@Transactional
class CatalogTypeMapperTest {

  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final String SOURCE = "OFFICIAL:romand.co.kr";

  @Autowired private EntityManager em;
  @Autowired private ProductTypeRepository typeRepository;
  @Autowired private CatalogTypeMapper shipped;

  private CatalogTypeMapper mapper;

  @BeforeEach
  void setUp() {
    ProductCategory lip = new ProductCategory("LIP", "립", true, true, 5);
    ProductCategory cheek = new ProductCategory("CHEEK", "치크", true, true, 4);
    em.persist(lip);
    em.persist(cheek);
    em.persist(new ProductType("LIP_TINT", lip, "립틴트", 3));
    em.persist(new ProductType("LIPSTICK", lip, "립스틱", 1));
    em.persist(new ProductType("BLUSHER", cheek, "블러셔", 1));
    em.flush();
    em.clear();
    mapper =
        new CatalogTypeMapper(
            typeRepository,
            TypeMappingTable.fromJson(
                MAPPER.readTree(
                    """
                    {"entries": [
                      {"source": "OFFICIAL:romand.co.kr", "categoryPath": ["립", "틴트"], "type": "LIP_TINT"},
                      {"source": "OFFICIAL:romand.co.kr", "categoryPath": ["없는 종류"], "type": "NO_SUCH_TYPE"}
                    ]}""")));
  }

  @Test
  void mappingTableWinsAndTheCategoryComesFromTheType() {
    var result = mapper.resolve(SOURCE, List.of("립", "틴트"), "CHEEK", "BLUSHER");

    assertThat(result).contains(new TypeResolution("LIP", "LIP_TINT", Origin.MAPPING));
  }

  @Test
  void hintIsAcceptedWhenTheTypeExistsAndMatchesTheCategoryHint() {
    assertThat(mapper.resolve(SOURCE, List.of("기타"), "CHEEK", "BLUSHER"))
        .contains(new TypeResolution("CHEEK", "BLUSHER", Origin.HINT));
    // 카테고리 힌트가 없으면 종류만으로 받는다
    assertThat(mapper.resolve(SOURCE, List.of(), null, "LIPSTICK"))
        .contains(new TypeResolution("LIP", "LIPSTICK", Origin.HINT));
  }

  @Test
  void hintIsRejectedWhenTheTypeIsUnknownOrBelongsToAnotherCategory() {
    assertThat(mapper.resolve(SOURCE, List.of("기타"), "CHEEK", "LIP_TINT")).isEmpty();
    assertThat(mapper.resolve(SOURCE, List.of("기타"), "LIP", "NO_SUCH_TYPE")).isEmpty();
  }

  @Test
  void categoryHintAloneCannotDecideAType() {
    assertThat(mapper.resolve(SOURCE, List.of("기타"), "LIP", null)).isEmpty();
  }

  @Test
  void mappedTypeThatIsNotInTheDatabaseFallsBackToTheHint() {
    assertThat(mapper.resolve(SOURCE, List.of("없는 종류"), "LIP", "LIPSTICK"))
        .contains(new TypeResolution("LIP", "LIPSTICK", Origin.HINT));
    assertThat(mapper.resolve(SOURCE, List.of("없는 종류"), null, null)).isEmpty();
  }

  @Test
  void nothingToGoOnMeansUnclassified() {
    assertThat(mapper.resolve(SOURCE, List.of("기타"), null, null)).isEmpty();
  }

  @Test
  void theShippedMapperIsWiredAndAnswersFromHintsWhenTheTableIsEmpty() {
    assertThat(shipped.resolve(SOURCE, List.of("립"), "LIP", "LIP_TINT"))
        .contains(new TypeResolution("LIP", "LIP_TINT", Origin.HINT));
  }
}
