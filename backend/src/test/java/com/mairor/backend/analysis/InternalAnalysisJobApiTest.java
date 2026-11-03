package com.mairor.backend.analysis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.jayway.jsonpath.JsonPath;
import com.mairor.backend.common.security.InternalTokenFilter;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

/** 운영자 분석 작업 API: 공유 토큰 인증, 입력 검증, 새 작업·합류, 조회. 세션·CSRF 없이 토큰만으로 통과해야 한다. */
@AutoConfigureMockMvc
class InternalAnalysisJobApiTest extends AnalysisIntegrationTest {

  private static final String URL = "/v1/internal/analysis-jobs";
  private static final String BODY =
      """
      {"youtubeVideoId": "VxAXD6PP76I", "sourceObjectKey": "videos/VxAXD6PP76I/source.mp4",
       "title": "완성도 up! 요즘 진짜 예뻐진 메이크업", "channelTitle": "GO지승", "durationSeconds": 1858}
      """;

  @Autowired private MockMvc mockMvc;

  @Test
  void withoutTokenIsUnauthorized() throws Exception {
    mockMvc
        .perform(post(URL).contentType(MediaType.APPLICATION_JSON).content(BODY))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
  }

  @Test
  void wrongTokenIsUnauthorized() throws Exception {
    mockMvc
        .perform(
            post(URL)
                .header(InternalTokenFilter.HEADER, "wrong")
                .contentType(MediaType.APPLICATION_JSON)
                .content(BODY))
        .andExpect(status().isUnauthorized());
  }

  @Test
  void registersANewJobThenJoinsItForTheSameVideo() throws Exception {
    String first =
        mockMvc
            .perform(
                post(URL)
                    .header(InternalTokenFilter.HEADER, TOKEN)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(BODY))
            .andExpect(status().isAccepted())
            .andExpect(jsonPath("$.receiptType").value("NEW_JOB"))
            .andExpect(jsonPath("$.status").value("PENDING"))
            .andExpect(jsonPath("$.progressStage").value("QUEUED"))
            .andReturn()
            .getResponse()
            .getContentAsString();
    String jobId = JsonPath.read(first, "$.jobId");

    mockMvc
        .perform(
            post(URL)
                .header(InternalTokenFilter.HEADER, TOKEN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(BODY))
        .andExpect(status().isAccepted())
        .andExpect(jsonPath("$.receiptType").value("JOINED_JOB"))
        .andExpect(jsonPath("$.jobId").value(jobId));

    assertThat(jdbc.queryForObject("select count(*) from analysis_jobs", Integer.class))
        .isEqualTo(1);
    mockMvc
        .perform(get(URL + "/" + jobId).header(InternalTokenFilter.HEADER, TOKEN))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.youtubeVideoId").value("VxAXD6PP76I"))
        .andExpect(jsonPath("$.source.objectKey").value("videos/VxAXD6PP76I/source.mp4"))
        .andExpect(jsonPath("$.source.width").doesNotExist())
        .andExpect(jsonPath("$.failureCode").doesNotExist());
  }

  @Test
  void invalidInputIsRejected() throws Exception {
    mockMvc
        .perform(
            post(URL)
                .header(InternalTokenFilter.HEADER, TOKEN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    """
                    {"youtubeVideoId": "short", "sourceObjectKey": "../etc/passwd",
                     "title": "", "channelTitle": "c", "durationSeconds": 0}
                    """))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
  }

  @Test
  void unknownJobIsNotFound() throws Exception {
    mockMvc
        .perform(get(URL + "/" + UUID.randomUUID()).header(InternalTokenFilter.HEADER, TOKEN))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOT_FOUND"));
  }
}
