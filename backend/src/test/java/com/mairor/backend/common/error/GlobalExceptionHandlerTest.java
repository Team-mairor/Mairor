package com.mairor.backend.common.error;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
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

@Import(TestcontainersConfiguration.class)
@SpringBootTest(properties = "test.error-probe=true")
@AutoConfigureMockMvc
@WithMockUser
class GlobalExceptionHandlerTest {

  @Autowired private MockMvc mockMvc;

  @Test
  void bodyValidation_returns400WithFieldDetails() throws Exception {
    mockMvc
        .perform(
            post("/v1/error-probe/body")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"\",\"count\":0}"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.message").value("입력값이 올바르지 않습니다."))
        .andExpect(jsonPath("$.details.length()").value(2))
        .andExpect(
            jsonPath("$.details[*].field").value(org.hamcrest.Matchers.hasItems("name", "count")));
  }

  @Test
  void storeUnavailable_returns503NotAServerBug() throws Exception {
    for (String path :
        new String[] {
          "/v1/error-probe/store-down",
          "/v1/error-probe/store-timeout",
          "/v1/error-probe/store-pool",
          "/v1/error-probe/store-rollback"
        }) {
      mockMvc
          .perform(get(path))
          .andExpect(status().isServiceUnavailable())
          .andExpect(jsonPath("$.code").value("SERVICE_UNAVAILABLE"))
          .andExpect(jsonPath("$.message").value(not(containsString("connection"))));
    }
  }

  @Test
  void anUnclassifiedRawSqlException_isNotTreatedAsAnOutage() throws Exception {
    mockMvc
        .perform(get("/v1/error-probe/store-raw-sql"))
        .andExpect(status().isInternalServerError())
        .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"));
  }

  @Test
  void otherDatabaseErrors_stayAn500WithoutLeakingDetails() throws Exception {
    mockMvc
        .perform(get("/v1/error-probe/store-bug"))
        .andExpect(status().isInternalServerError())
        .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
        .andExpect(jsonPath("$.message").value(not(containsString("duplicate"))));
  }

  @Test
  void malformedJson_returns400() throws Exception {
    mockMvc
        .perform(
            post("/v1/error-probe/body")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{not json"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value("body"));
  }

  @Test
  void unsupportedContentType_returns415() throws Exception {
    mockMvc
        .perform(
            post("/v1/error-probe/body")
                .with(csrf())
                .contentType(MediaType.TEXT_PLAIN)
                .content("name"))
        .andExpect(status().isUnsupportedMediaType())
        .andExpect(jsonPath("$.code").value("UNSUPPORTED_MEDIA_TYPE"))
        .andExpect(jsonPath("$.details").doesNotExist())
        .andExpect(header().exists("Accept"));
  }

  @Test
  void unknownPath_returns404() throws Exception {
    mockMvc
        .perform(get("/v1/nope"))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOT_FOUND"))
        .andExpect(jsonPath("$.message").value("요청한 리소스를 찾을 수 없습니다."))
        .andExpect(jsonPath("$.details").doesNotExist());
  }

  @Test
  void wrongMethod_returns405() throws Exception {
    mockMvc
        .perform(post("/health").with(csrf()))
        .andExpect(status().isMethodNotAllowed())
        .andExpect(jsonPath("$.code").value("METHOD_NOT_ALLOWED"))
        .andExpect(jsonPath("$.message").value("허용되지 않는 요청 방식입니다."))
        .andExpect(header().exists("Allow"));
  }

  @Test
  void businessConflict_returnsDomainCode() throws Exception {
    mockMvc
        .perform(get("/v1/error-probe/conflict"))
        .andExpect(status().isConflict())
        .andExpect(jsonPath("$.code").value("ANALYSIS_IN_PROGRESS"))
        .andExpect(jsonPath("$.message").value("이미 분석 중인 영상입니다."));
  }

  @Test
  void businessNotFound_usesCommonCode() throws Exception {
    mockMvc
        .perform(get("/v1/error-probe/missing"))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOT_FOUND"));
  }

  @Test
  void tooManyRequests_returns429WithRetryAfter() throws Exception {
    mockMvc
        .perform(get("/v1/error-probe/limit"))
        .andExpect(status().isTooManyRequests())
        .andExpect(header().string("Retry-After", "30"))
        .andExpect(jsonPath("$.code").value("TOO_MANY_REQUESTS"));
  }

  @Test
  void unexpected_returns500WithoutInternalDetail() throws Exception {
    mockMvc
        .perform(get("/v1/error-probe/boom"))
        .andExpect(status().isInternalServerError())
        .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
        .andExpect(jsonPath("$.message").value("서버에서 예기치 않은 오류가 발생했습니다."))
        .andExpect(
            content()
                .string(
                    org.hamcrest.Matchers.not(
                        org.hamcrest.Matchers.containsString("must not leak"))));
  }
}
