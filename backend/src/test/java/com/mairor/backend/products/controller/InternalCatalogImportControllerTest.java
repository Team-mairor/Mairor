package com.mairor.backend.products.controller;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.common.security.InternalTokenFilter;
import com.mairor.backend.products.entity.ColorSource;
import com.mairor.backend.products.entity.NameSource;
import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductShadeColor;
import com.mairor.backend.products.entity.ProductType;
import com.mairor.backend.products.entity.ReviewStatus;
import jakarta.persistence.EntityManager;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.time.Instant;
import java.util.function.Consumer;
import javax.sql.DataSource;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.core.io.ClassPathResource;
import org.springframework.http.MediaType;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.jdbc.datasource.init.ScriptUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/**
 * 수집 상품 판정 시험 API 의 인증·요청 검증·응답 계약. 판정 규칙 자체는 {@code CatalogMatchPlannerTest}가 본다. 데이터는 운영 카테고리 시드와
 * 테스트가 만든 제품이고 끝나면 되돌린다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql",
      "app.security.allowed-origins=http://localhost:3000",
      "app.internal.token=" + InternalCatalogImportControllerTest.TOKEN
    })
@AutoConfigureMockMvc
@Transactional
class InternalCatalogImportControllerTest {

  static final String TOKEN = "test-internal-token";
  private static final String PATH = "/v1/internal/catalog/import-runs/dry-run";
  private static final Path SAMPLES = Path.of("..", "shared", "catalog-import", "samples");
  private static final ObjectMapper MAPPER = new ObjectMapper();

  @Autowired private MockMvc mockMvc;
  @Autowired private DataSource dataSource;
  @Autowired private EntityManager em;

  @BeforeEach
  void setUp() {
    Connection connection = DataSourceUtils.getConnection(dataSource);
    try {
      ScriptUtils.executeSqlScript(
          connection, new ClassPathResource("db/seed/product-categories.sql"));
    } finally {
      DataSourceUtils.releaseConnection(connection, dataSource);
    }
  }

  private static ObjectNode sample(String file, Consumer<ObjectNode> change) throws Exception {
    ObjectNode node = (ObjectNode) MAPPER.readTree(Files.readString(SAMPLES.resolve(file)));
    change.accept(node);
    return node;
  }

  private static String body(ObjectNode... items) {
    ObjectNode root = MAPPER.createObjectNode();
    ArrayNode array = root.putArray("items");
    for (ObjectNode item : items) {
      array.add(item);
    }
    return MAPPER.writeValueAsString(root);
  }

  private MockHttpServletRequestBuilder authorized(String json) {
    return post(PATH)
        .header(InternalTokenFilter.HEADER, TOKEN)
        .contentType(MediaType.APPLICATION_JSON)
        .content(json);
  }

  // --- 인증 ---

  @Test
  void withoutTheInternalTokenTheRequestIsRejected() throws Exception {
    mockMvc
        .perform(post(PATH).contentType(MediaType.APPLICATION_JSON).content(body()))
        .andExpect(status().isUnauthorized());
    mockMvc
        .perform(
            post(PATH)
                .header(InternalTokenFilter.HEADER, "wrong")
                .contentType(MediaType.APPLICATION_JSON)
                .content(body()))
        .andExpect(status().isUnauthorized());
  }

  // --- 요청 검증 ---

  @Test
  void itemsMustBeANonEmptyArrayOfAtMostOneHundred() throws Exception {
    for (String json :
        new String[] {
          "{}", "{\"items\": {}}", "{\"items\": \"x\"}", "{\"items\": []}", "{\"items\": null}"
        }) {
      mockMvc
          .perform(authorized(json))
          .andExpect(status().isBadRequest())
          .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
          .andExpect(jsonPath("$.details[0].field").value("items"));
    }
    ObjectNode[] tooMany = new ObjectNode[101];
    for (int i = 0; i < tooMany.length; i++) {
      tooMany[i] = MAPPER.createObjectNode();
    }
    mockMvc
        .perform(authorized(body(tooMany)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].reason").value("items 는 100건까지입니다."));
  }

  @Test
  void aBodyThatIsNotJsonIsABadRequest() throws Exception {
    mockMvc.perform(authorized("not json")).andExpect(status().isBadRequest());
  }

  @Test
  void exactlyOneHundredItemsAreAccepted() throws Exception {
    ObjectNode[] items = new ObjectNode[100];
    for (int i = 0; i < items.length; i++) {
      items[i] = MAPPER.createObjectNode();
    }

    mockMvc
        .perform(authorized(body(items)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.results.length()").value(100))
        .andExpect(jsonPath("$.results[0].outcome").value("INVALID"));
  }

  // --- 건별 판정 ---

  @Test
  void eachItemGetsItsOwnResultInRequestOrderAndABrokenItemDoesNotFailTheRequest()
      throws Exception {
    ObjectNode good = sample("etude_option_image.json", n -> {});
    ObjectNode broken = sample("invalid_incomplete_source.json", n -> {});

    mockMvc
        .perform(authorized(body(good, broken)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.results.length()").value(2))
        .andExpect(jsonPath("$.results[0].index").value(0))
        .andExpect(jsonPath("$.results[0].itemKey").value("000003"))
        .andExpect(jsonPath("$.results[0].outcome").value("CREATED"))
        .andExpect(jsonPath("$.results[0].productId").value((Object) null))
        .andExpect(jsonPath("$.results[0].reasons.length()").value(0))
        .andExpect(jsonPath("$.results[0].issues.length()").value(0))
        .andExpect(jsonPath("$.results[1].index").value(1))
        .andExpect(jsonPath("$.results[1].itemKey").value("000004"))
        .andExpect(jsonPath("$.results[1].outcome").value("INVALID"))
        .andExpect(jsonPath("$.results[1].issues.length()").value(2))
        .andExpect(
            jsonPath("$.results[1].issues[?(@.path == 'sourceProductId')].code").value("REQUIRED"))
        .andExpect(
            jsonPath("$.results[1].issues[?(@.path == 'shades[0].colors[0].hex')].code")
                .value("INVALID_FORMAT"));
  }

  @Test
  void aNonObjectItemIsInvalidAndAnUnknownTypeIsUnclassified() throws Exception {
    ObjectNode unclassified =
        sample(
            "etude_option_image.json",
            n -> {
              n.put("typeHint", "NO_SUCH_TYPE");
              n.remove("categoryHint");
            });
    ObjectNode notAnObject = MAPPER.createObjectNode();

    mockMvc
        .perform(authorized(body(unclassified, notAnObject)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.results[0].outcome").value("UNCLASSIFIED"))
        .andExpect(jsonPath("$.results[1].outcome").value("INVALID"))
        .andExpect(jsonPath("$.results[1].itemKey").value((Object) null));
  }

  /** 같은 출처·상품 번호로 이미 저장된 제품. {@code operatorCorrected}면 색을 운영이 정정한 값으로 둔다. */
  private Product storeEtudeProduct(boolean operatorCorrected) {
    ProductType mascara = em.find(ProductType.class, "MASCARA");
    Product stored = new Product(mascara, "에뛰드", "예시 컬 픽스 마스카라");
    stored.recordSource(
        "OFFICIAL:etude.com",
        "example-curl-fix-mascara",
        "https://www.etude.com/x",
        Instant.parse("2026-11-01T00:00:00Z"));
    ProductShade black = stored.addShade("01 블랙", 1, null);
    black.changeSourceOptionId("01-black");
    ProductShadeColor slot = black.addColor(1, null, NameSource.NONE);
    slot.assignColor(
        ColorSource.PRODUCT_PHOTO,
        "#1E1B1C",
        true,
        ReviewStatus.AUTO_APPROVED,
        Instant.parse("2026-11-01T00:00:00Z"));
    if (operatorCorrected) {
      slot.changeReviewStatus(ReviewStatus.APPROVED);
    }
    em.persist(stored);
    em.flush();
    em.clear();
    return stored;
  }

  @Test
  void anExistingProductIsUpdatedAndReturnsItsId() throws Exception {
    Product stored = storeEtudeProduct(false);

    mockMvc
        .perform(authorized(body(sample("etude_option_image.json", n -> {}))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.results[0].outcome").value("UPDATED"))
        .andExpect(jsonPath("$.results[0].productId").value(stored.getId().toString()))
        // 같은 값이면 판정과 상관없이 쓰던 색을 그대로 둔다(임계값을 정하지 않은 설정이어도)
        .andExpect(jsonPath("$.results[0].reasons.length()").value(0));
  }

  @Test
  void aPartialResultListsItsReasons() throws Exception {
    Product stored = storeEtudeProduct(true);

    // 운영이 정정한 색은 수집이 바꾸지 않는다
    ObjectNode differentColor =
        sample(
            "etude_option_image.json",
            n ->
                ((ObjectNode) n.path("shades").get(0).path("colors").get(0)).put("hex", "#E8452C"));

    mockMvc
        .perform(authorized(body(differentColor)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.results[0].outcome").value("PARTIAL"))
        .andExpect(jsonPath("$.results[0].productId").value(stored.getId().toString()))
        .andExpect(jsonPath("$.results[0].reasons[0]").value("COLOR_KEPT_OPERATOR"));
  }

  @Test
  void aDryRunNeverWritesAnything() throws Exception {
    long products = count("Product");
    long shades = count("ProductShade");
    long colors = count("ProductShadeColor");

    mockMvc
        .perform(authorized(body(sample("etude_option_image.json", n -> {}))))
        .andExpect(status().isOk());
    em.flush();

    assertThat(count("Product")).isEqualTo(products);
    assertThat(count("ProductShade")).isEqualTo(shades);
    assertThat(count("ProductShadeColor")).isEqualTo(colors);
  }

  private long count(String entity) {
    return em.createQuery("select count(e) from " + entity + " e", Long.class).getSingleResult();
  }
}
