package com.mairor.backend.products.controller;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.common.security.InternalTokenFilter;
import com.mairor.backend.products.imports.CatalogMatchPlanner;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/**
 * 판정 시험에서 한 건의 판정이 예외로 실패해도 응답 전체가 500 이 되지 않고 나머지 건이 판정되는지 본다.
 *
 * <p>트랜잭션 프록시를 실제로 거쳐야 하므로 테스트 자체는 트랜잭션으로 감싸지 않는다({@code @Transactional} 을 붙이면 모든 호출이 테스트의 트랜잭션에
 * 참여해서 문제가 가려진다). 판정 단계({@code CatalogMatchPlanner})만 스파이로 바꿔 예외를 던지게 하고, 나머지는 실제 빈을 쓴다. 데이터는 만들지
 * 않으며 분류할 수 없는 상품({@code UNCLASSIFIED})은 DB 에 아무것도 없어도 판정된다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql",
      "app.security.allowed-origins=http://localhost:3000",
      "app.internal.token=" + InternalCatalogImportFailureIsolationTest.TOKEN
    })
@AutoConfigureMockMvc
class InternalCatalogImportFailureIsolationTest {

  static final String TOKEN = "test-internal-token";
  private static final String PATH = "/v1/internal/catalog/import-runs/dry-run";
  private static final Path SAMPLE =
      Path.of("..", "shared", "catalog-import", "samples", "etude_option_image.json");
  private static final ObjectMapper MAPPER = new ObjectMapper();

  @Autowired private MockMvc mockMvc;
  @MockitoSpyBean private CatalogMatchPlanner planner;

  /** 분류할 수 없는 상품 한 건. DB 에 카테고리가 없어도 판정할 수 있다. */
  private static ObjectNode unclassifiable(String itemKey, String productId) throws Exception {
    ObjectNode node = (ObjectNode) MAPPER.readTree(Files.readString(SAMPLE));
    node.put("itemKey", itemKey);
    node.put("sourceProductId", productId);
    node.put("typeHint", "NO_SUCH_TYPE");
    node.remove("categoryHint");
    node.remove("shades");
    return node;
  }

  private String body(ObjectNode... items) {
    ObjectNode root = MAPPER.createObjectNode();
    ArrayNode array = root.putArray("items");
    for (ObjectNode item : items) {
      array.add(item);
    }
    return MAPPER.writeValueAsString(root);
  }

  @Test
  void anExceptionWhilePlanningOneItemFailsOnlyThatItemAndTheRequestStillSucceeds()
      throws Exception {
    doThrow(new IllegalStateException("boom")).doCallRealMethod().when(planner).plan(any());

    mockMvc
        .perform(
            post(PATH)
                .header(InternalTokenFilter.HEADER, TOKEN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(body(unclassifiable("000001", "p-1"), unclassifiable("000002", "p-2"))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.results.length()").value(2))
        .andExpect(jsonPath("$.results[0].outcome").value("FAILED"))
        .andExpect(jsonPath("$.results[0].itemKey").value("000001"))
        .andExpect(jsonPath("$.results[1].outcome").value("UNCLASSIFIED"))
        .andExpect(jsonPath("$.results[1].itemKey").value("000002"));
  }

  @Test
  void aDatabaseErrorWhilePlanningOneItemDoesNotSpoilTheItemsAfterIt() throws Exception {
    doThrow(new DataIntegrityViolationException("db")).doCallRealMethod().when(planner).plan(any());

    mockMvc
        .perform(
            post(PATH)
                .header(InternalTokenFilter.HEADER, TOKEN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    body(
                        unclassifiable("000001", "p-1"),
                        unclassifiable("000002", "p-2"),
                        unclassifiable("000003", "p-3"))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.results[0].outcome").value("FAILED"))
        .andExpect(jsonPath("$.results[1].outcome").value("UNCLASSIFIED"))
        .andExpect(jsonPath("$.results[2].outcome").value("UNCLASSIFIED"));
  }
}
