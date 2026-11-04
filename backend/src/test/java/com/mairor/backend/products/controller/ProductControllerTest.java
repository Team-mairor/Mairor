package com.mairor.backend.products.controller;

import static org.hamcrest.Matchers.containsInAnyOrder;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.entity.ProductType;
import com.mairor.backend.products.entity.ShadeColor;
import com.mairor.backend.users.support.AuthenticatedUser;
import jakarta.persistence.EntityManager;
import java.sql.Connection;
import java.util.List;
import java.util.UUID;
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
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import org.springframework.transaction.annotation.Transactional;

/**
 * 제품 검색·상세 조회 API 의 요청 검증·인증·JSON 계약을 확인한다. 검색 일치 규칙·정렬·쿼리 수는 {@code ProductSearchServiceTest} 가
 * 본다.
 *
 * <p>운영 카테고리 시드를 테스트 트랜잭션의 연결로 넣고, 제품은 테스트가 직접 만든다. 테스트가 끝나면 모두 되돌린다. 로그인은 세션 없이 인증 정보만 붙인다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql",
      "app.security.allowed-origins=http://localhost:3000"
    })
@AutoConfigureMockMvc
@Transactional
class ProductControllerTest {

  private static final String PATH = "/v1/products";
  private static final String NBSP = Character.toString(0x00A0);
  private static final String BRAND = "롬앤";
  private static final String NAME = "쥬시 래스팅 틴트";

  @Autowired private MockMvc mockMvc;
  @Autowired private DataSource dataSource;
  @Autowired private EntityManager em;

  private Product tint;

  @BeforeEach
  void setUp() {
    Connection connection = DataSourceUtils.getConnection(dataSource);
    try {
      ScriptUtils.executeSqlScript(
          connection, new ClassPathResource("db/seed/product-categories.sql"));
    } finally {
      DataSourceUtils.releaseConnection(connection, dataSource);
    }
    tint = new Product(em.find(ProductType.class, "LIP_TINT"), BRAND, NAME);
    tint.addShade("01 누드 로즈", 1, ShadeColor.of("#D08A86", "SAMPLE", false));
    tint.addShade("03 로지", 2, null);
    em.persist(tint);
    em.flush();
  }

  private static RequestPostProcessor member() {
    return authentication(
        UsernamePasswordAuthenticationToken.authenticated(
            new AuthenticatedUser(UUID.randomUUID(), "member@example.com"),
            null,
            List.of(new SimpleGrantedAuthority("ROLE_USER"))));
  }

  private static MockHttpServletRequestBuilder search(
      String category, String type, String brand, String name) {
    MockHttpServletRequestBuilder request = get(PATH).with(member());
    if (category != null) {
      request.queryParam("category", category);
    }
    if (type != null) {
      request.queryParam("type", type);
    }
    if (brand != null) {
      request.queryParam("brand", brand);
    }
    if (name != null) {
      request.queryParam("name", name);
    }
    return request;
  }

  @Test
  void search_returnsTheProductInTheContractShape() throws Exception {
    mockMvc
        .perform(search("LIP", "LIP_TINT", BRAND, NAME))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.length()").value(1))
        .andExpect(jsonPath("$.items.length()").value(1))
        .andExpect(jsonPath("$.items[0].length()").value(6))
        .andExpect(jsonPath("$.items[0].productId").value(tint.getId().toString()))
        .andExpect(jsonPath("$.items[0].brand").value(BRAND))
        .andExpect(jsonPath("$.items[0].name").value(NAME))
        .andExpect(jsonPath("$.items[0].category").value("LIP"))
        .andExpect(jsonPath("$.items[0].type").value("LIP_TINT"))
        .andExpect(jsonPath("$.items[0].shades.length()").value(2))
        .andExpect(jsonPath("$.items[0].shades[0].length()").value(3))
        .andExpect(jsonPath("$.items[0].shades[0].shadeId").isString())
        .andExpect(jsonPath("$.items[0].shades[0].name").value("01 누드 로즈"))
        .andExpect(jsonPath("$.items[0].shades[0].color.length()").value(4))
        .andExpect(jsonPath("$.items[0].shades[0].color.colorSpace").value("sRGB"))
        .andExpect(jsonPath("$.items[0].shades[0].color.hex").value("#D08A86"))
        .andExpect(jsonPath("$.items[0].shades[0].color.source").value("CATALOG"))
        .andExpect(jsonPath("$.items[0].shades[0].color.estimated").value(false))
        // 색을 모르면 필드를 빼지 않고 null 로 보낸다
        .andExpect(jsonPath("$.items[0].shades[1].color").value((Object) null))
        .andExpect(jsonPath("$.items[0].shades[1].length()").value(3));
  }

  @Test
  void search_findsByKoreanQueryWithCaseAndWhitespaceDifferences() throws Exception {
    mockMvc
        .perform(search("LIP", "LIP_TINT", NBSP + BRAND + " ", "쥬시   래스팅" + NBSP + "틴트"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items[0].name").value(NAME));
  }

  @Test
  void search_withoutAMatchIsAnEmptyListNotNotFound() throws Exception {
    mockMvc
        .perform(search("LIP", "LIP_TINT", BRAND, "없는 틴트"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items").isArray())
        .andExpect(jsonPath("$.items.length()").value(0));
  }

  @Test
  void search_missingParametersAreReportedTogether() throws Exception {
    mockMvc
        .perform(search(null, null, null, null))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(
            jsonPath(
                "$.details[*].field", containsInAnyOrder("category", "type", "brand", "name")));
  }

  @Test
  void search_blankOrNbspOnlyTextIsRequired() throws Exception {
    mockMvc
        .perform(search("LIP", "LIP_TINT", " ", NBSP + NBSP))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[*].field", containsInAnyOrder("brand", "name")))
        .andExpect(jsonPath("$.details[*].reason", containsInAnyOrder("필수 값입니다.", "필수 값입니다.")));
  }

  @Test
  void search_lengthLimitsFollowTheCatalogEntity() throws Exception {
    String brandAtLimit = "b".repeat(Product.BRAND_MAX_LENGTH);
    String nameAtLimit = "n".repeat(Product.NAME_MAX_LENGTH);

    // 상한까지는 형식 검사를 통과한다 (앞뒤 공백은 세지 않는다)
    mockMvc
        .perform(search("LIP", "LIP_TINT", " " + brandAtLimit + NBSP, nameAtLimit))
        .andExpect(status().isOk());
    mockMvc
        .perform(search("LIP", "LIP_TINT", brandAtLimit + "b", nameAtLimit + "n"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[*].field", containsInAnyOrder("brand", "name")))
        .andExpect(
            jsonPath(
                "$.details[*].reason", containsInAnyOrder("100자 이하여야 합니다.", "200자 이하여야 합니다.")));
  }

  @Test
  void search_typeOfAnotherCategoryIsATypeError() throws Exception {
    mockMvc
        .perform(search("LIP", "CUSHION", BRAND, NAME))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details.length()").value(1))
        .andExpect(jsonPath("$.details[0].field").value("type"));
  }

  @Test
  void search_unknownCategoryWithAnExistingTypeIsACategoryError() throws Exception {
    mockMvc
        .perform(search("UNKNOWN", "LIP_TINT", BRAND, NAME))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details.length()").value(1))
        .andExpect(jsonPath("$.details[0].field").value("category"));
  }

  @Test
  void get_returnsTheSameShapeAsASearchItem() throws Exception {
    mockMvc
        .perform(get(PATH + "/" + tint.getId()).with(member()))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.length()").value(6))
        .andExpect(jsonPath("$.productId").value(tint.getId().toString()))
        .andExpect(jsonPath("$.category").value("LIP"))
        .andExpect(jsonPath("$.shades.length()").value(2));
  }

  @Test
  void get_unknownProductIsNotFound() throws Exception {
    mockMvc
        .perform(get(PATH + "/" + UUID.randomUUID()).with(member()))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOT_FOUND"));
  }

  @Test
  void get_productIdThatIsNotAUuidIsAValidationError() throws Exception {
    mockMvc
        .perform(get(PATH + "/not-a-uuid").with(member()))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value("productId"));
  }

  @Test
  void anonymous_isRejectedForSearchAndDetail() throws Exception {
    mockMvc
        .perform(
            get(PATH)
                .queryParam("category", "LIP")
                .queryParam("type", "LIP_TINT")
                .queryParam("brand", BRAND)
                .queryParam("name", NAME))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
    mockMvc
        .perform(get(PATH + "/" + tint.getId()))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
  }
}
