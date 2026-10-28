package com.mairor.backend.common.web;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
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
import org.springframework.test.web.servlet.MockMvc;

/** 개발(dev) 기본 설정: API 문서와 Swagger UI 가 로그인 없이 열리고, 다른 API 는 그대로 보호된다. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiDocsTest {

  @Autowired private MockMvc mockMvc;

  @Test
  void apiDocs_isPublicAndDescribesTheApi() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
        .andExpect(jsonPath("$.openapi").exists())
        .andExpect(jsonPath("$.paths['/health']").exists());
  }

  @Test
  void apiDocs_includesSignUp() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.paths['/v1/users/signup'].post").exists());
  }

  /** Swagger UI 의 기본 입력이 "string" 이 아니라 바로 보낼 수 있는 값(필수 약관 3개 포함)이어야 한다. */
  @Test
  void apiDocs_signUpHasUsableExample() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(
            jsonPath(
                    "$.paths['/v1/users/signup'].post.requestBody.content['application/json'].examples")
                .isNotEmpty())
        .andExpect(
            jsonPath("$.components.schemas.SignupAgreement.properties.version.example")
                .value("2026-10-26"))
        .andExpect(
            jsonPath("$.components.schemas.SignupAgreement.properties.type.example").value("TERMS"))
        .andExpect(
            jsonPath("$.components.schemas.SignUpRequest.properties.email.example")
                .value("user@example.com"));
  }

  @Test
  void apiDocs_includesEmailVerification() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.paths['/v1/users/email-verification'].post").exists())
        .andExpect(jsonPath("$.paths['/v1/users/email-verification/verification'].post").exists());
  }

  @Test
  void apiDocs_includesEmailAvailability() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.paths['/v1/users/email-availability'].post").exists());
  }

  @Test
  void swaggerUi_isPublic() throws Exception {
    mockMvc.perform(get("/swagger-ui/index.html")).andExpect(status().isOk());
  }

  @Test
  void swaggerUiConfig_isPublicSoTheScreenCanLoad() throws Exception {
    mockMvc
        .perform(get("/v3/api-docs/swagger-config"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.url").exists());
  }

  @Test
  void otherEndpoints_stillRequireLogin() throws Exception {
    mockMvc
        .perform(get("/v1/any"))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
  }
}
