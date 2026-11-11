package com.mairor.backend.products.controller;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.users.support.AuthenticatedUser;
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
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import org.springframework.transaction.annotation.Transactional;

/**
 * 카테고리·종류 목록 API 의 인증과 JSON 계약을 확인한다. 묶기·정렬은 {@code ProductCategoryServiceTest}, 시드 값 전체는 {@code
 * ProductSeedSqlTest} 가 검증하므로 여기서는 대표값만 본다.
 *
 * <p>운영 시드를 테스트 트랜잭션의 연결로 넣어서 테스트가 끝나면 함께 되돌린다. 로그인은 세션 없이 인증 정보만 붙인다(세션이 없는 요청은 절대 만료 검사 대상이 아니다).
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql",
      "app.security.allowed-origins=http://localhost:3000"
    })
@AutoConfigureMockMvc
@Transactional
class ProductCategoryControllerTest {

  private static final String PATH = "/v1/product-categories";

  @Autowired private MockMvc mockMvc;
  @Autowired private DataSource dataSource;

  @BeforeEach
  void applyCategorySeed() {
    Connection connection = DataSourceUtils.getConnection(dataSource);
    try {
      ScriptUtils.executeSqlScript(
          connection, new ClassPathResource("db/seed/product-categories.sql"));
    } finally {
      DataSourceUtils.releaseConnection(connection, dataSource);
    }
  }

  private static RequestPostProcessor member() {
    return authentication(
        UsernamePasswordAuthenticationToken.authenticated(
            new AuthenticatedUser(UUID.randomUUID(), "member@example.com"),
            null,
            List.of(new SimpleGrantedAuthority("ROLE_USER"))));
  }

  @Test
  void member_getsCategoriesInTheContractShape() throws Exception {
    mockMvc
        .perform(get(PATH).with(member()))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.items").isArray())
        .andExpect(jsonPath("$.items.length()").value(9))
        .andExpect(jsonPath("$.items[0].code").value("BASE"))
        .andExpect(jsonPath("$.items[0].label").value("베이스"))
        .andExpect(jsonPath("$.items[0].matchable").isBoolean())
        .andExpect(jsonPath("$.items[0].shadeSelectable").isBoolean())
        .andExpect(jsonPath("$.items[0].types").isArray())
        .andExpect(jsonPath("$.items[0].types[0].code").isString())
        .andExpect(jsonPath("$.items[0].types[0].label").isString())
        .andExpect(jsonPath("$.items[0].compatibleParts").isArray())
        .andExpect(jsonPath("$.items[0].compatibleParts.length()").value(0));
  }

  @Test
  void member_getsOnlyTheContractFields() throws Exception {
    mockMvc
        .perform(get(PATH).with(member()))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.length()").value(1))
        .andExpect(jsonPath("$.items[0].length()").value(6))
        .andExpect(jsonPath("$.items[0].types[0].length()").value(2));
  }

  @Test
  void member_seesFragranceWithItsSingleTypeAndNoShades() throws Exception {
    mockMvc
        .perform(get(PATH).with(member()))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items[?(@.code == 'FRAGRANCE')].matchable").value(false))
        .andExpect(jsonPath("$.items[?(@.code == 'FRAGRANCE')].shadeSelectable").value(false))
        .andExpect(jsonPath("$.items[?(@.code == 'FRAGRANCE')].types[*].code").value("PERFUME"));
  }

  @Test
  void anonymous_isRejectedWithTheCommonError() throws Exception {
    mockMvc
        .perform(get(PATH))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.code").value("UNAUTHORIZED"))
        .andExpect(jsonPath("$.message").isString());
  }
}
