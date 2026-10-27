package com.mairor.backend.common.web;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

/**
 * 끄는 스위치가 실제로 막는지 확인한다. 운영 설정 파일에 그 값이 들어 있는지는 {@link OpenApiProdConfigTest} 가 확인한다. (여기서는 값을 테스트가
 * 직접 넣으므로 설정 파일이 바뀌어도 이 테스트는 영향을 받지 않는다.)
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {"springdoc.api-docs.enabled=false", "springdoc.swagger-ui.enabled=false"})
@AutoConfigureMockMvc
class OpenApiDocsDisabledTest {

  @Autowired private MockMvc mockMvc;

  @Test
  void apiDocs_isNotFoundWhenDisabled() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOT_FOUND"));
  }

  @Test
  void swaggerUi_isNotFoundWhenDisabled() throws Exception {
    mockMvc.perform(get("/swagger-ui/index.html")).andExpect(status().isNotFound());
    mockMvc.perform(get("/swagger-ui.html")).andExpect(status().isNotFound());
  }

  @Test
  void healthAndOtherEndpoints_areUnaffected() throws Exception {
    mockMvc.perform(get("/health")).andExpect(status().isOk());
    mockMvc.perform(get("/v1/guides")).andExpect(status().isUnauthorized());
  }
}
