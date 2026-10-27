package com.mairor.backend.common.security;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

/** 시큐리티 필터 단계의 오류 응답 (노션 API 명세 공통 오류 코드). */
@Import(TestcontainersConfiguration.class)
@SpringBootTest
@AutoConfigureMockMvc
class SecurityResponseTest {

  /** 컨트롤러가 없는 보호 경로. 필터가 먼저 막는지만 본다. */
  private static final String PROTECTED = "/v1/any";

  @Autowired private MockMvc mockMvc;

  @Test
  void unauthenticated_returns401Json() throws Exception {
    mockMvc
        .perform(get(PROTECTED))
        .andExpect(status().isUnauthorized())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.code").value("UNAUTHORIZED"))
        .andExpect(jsonPath("$.message").value("로그인이 필요합니다."));
  }

  @Test
  @WithMockUser
  void postWithoutCsrfToken_returns403CsrfInvalid() throws Exception {
    mockMvc
        .perform(post(PROTECTED))
        .andExpect(status().isForbidden())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.code").value("CSRF_INVALID"))
        .andExpect(jsonPath("$.message").value("요청 보안 토큰이 유효하지 않습니다."));
  }

  @Test
  @WithMockUser
  void postWithWrongCsrfToken_returns403CsrfInvalid() throws Exception {
    mockMvc
        .perform(post(PROTECTED).with(csrf().useInvalidToken()))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("CSRF_INVALID"));
  }

  /** CSRF 필터가 인가 검사보다 먼저 돌아서, 세션이 없어도 토큰이 없으면 401이 아니라 403 CSRF_INVALID가 나간다. */
  @Test
  void unauthenticatedPostWithoutCsrfToken_returns403CsrfInvalid() throws Exception {
    mockMvc
        .perform(post(PROTECTED))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("CSRF_INVALID"));
  }

  @Test
  void health_isPublic() throws Exception {
    mockMvc.perform(get("/health")).andExpect(status().isOk());
  }
}
