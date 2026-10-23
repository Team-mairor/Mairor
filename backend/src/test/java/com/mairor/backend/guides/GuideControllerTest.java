package com.mairor.backend.guides;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

/** 공통 템플릿 계약 테스트의 본보기: 페이지 파라미터 기본값·검증과 PageResponse 형식. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest
@AutoConfigureMockMvc
@WithMockUser
class GuideControllerTest {

  @Autowired private MockMvc mockMvc;

  @Test
  void list_withDefaults_returnsEmptyFirstPage() throws Exception {
    mockMvc
        .perform(get("/v1/guides"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items").isEmpty())
        .andExpect(jsonPath("$.page").value(0))
        .andExpect(jsonPath("$.size").value(20))
        .andExpect(jsonPath("$.hasNext").value(false));
  }

  @Test
  void list_echoesRequestedPageAndSize() throws Exception {
    mockMvc
        .perform(get("/v1/guides").param("page", "3").param("size", "50"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.page").value(3))
        .andExpect(jsonPath("$.size").value(50));
  }

  @Test
  void list_sizeOutOfRange_returns400WithDetail() throws Exception {
    mockMvc
        .perform(get("/v1/guides").param("size", "0"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value("size"));

    mockMvc
        .perform(get("/v1/guides").param("size", "101"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("size"));
  }

  @Test
  void list_negativePage_returns400WithDetail() throws Exception {
    mockMvc
        .perform(get("/v1/guides").param("page", "-1"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value("page"));
  }

  @Test
  void list_nonNumericPage_returns400() throws Exception {
    mockMvc
        .perform(get("/v1/guides").param("page", "abc"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
  }
}
