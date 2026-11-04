package com.mairor.backend.analysis;

import static org.hamcrest.Matchers.everyItem;
import static org.hamcrest.Matchers.hasSize;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.analysis.service.AnalysisJobRequest;
import com.mairor.backend.analysis.service.AnalysisJobService;
import com.mairor.backend.analysis.worker.AnalysisJobStore;
import com.mairor.backend.users.support.AuthenticatedUser;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.core.io.ClassPathResource;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

/**
 * API-ANALYSIS-001 가이드 조회 계약. AI 샘플 영상(eFzG30avtOI, 19단계)의 가이드 입력과 콜백 예시의 설명·영역으로 승인된 가이드를 만든다. 샘플
 * 가이드 입력은 화장 종류 10종 전이라 영역 샘플에 맞춰 s14 · s15 · s16 을 마스카라 · 쉐딩 · 하이라이트로 고쳐 두었다.
 */
@AutoConfigureMockMvc
class GuideApiTest extends AnalysisIntegrationTest {

  @Autowired private MockMvc mockMvc;
  @Autowired private AnalysisJobService service;
  @Autowired private AnalysisJobStore store;

  private static RequestPostProcessor member() {
    return authentication(
        UsernamePasswordAuthenticationToken.authenticated(
            new AuthenticatedUser(UUID.randomUUID(), "member@example.com"),
            null,
            List.of(new SimpleGrantedAuthority("ROLE_USER"))));
  }

  private static String resource(String path) throws IOException {
    return new ClassPathResource(path).getContentAsString(StandardCharsets.UTF_8);
  }

  /** 가이드 하나를 만들고 상태를 정한다. AI 결과(설명·영역)는 콜백 예시에서 가져온다. */
  private String guideWithStatus(String youtubeVideoId, String reviewStatus) throws IOException {
    UUID jobId =
        service
            .register(
                new AnalysisJobRequest(
                    youtubeVideoId,
                    "videos/" + youtubeVideoId + "/source.mp4",
                    "베이스부터 립까지",
                    "MAIROR",
                    525))
            .jobId();
    store.saveGuideInput(jobId, resource("analysis/guide-input-eFzG30avtOI.json"));
    JsonNode callback =
        JsonMapper.builder().build().readTree(resource("analysis/ai-callback-completed.json"));
    jdbc.update(
        "update guides set explanation = ?::jsonb, area = ?::jsonb, mesh_version = 'v1',"
            + " review_status = ? where analysis_job_id = ?",
        callback.get("guide").toString(),
        callback.get("area").toString(),
        reviewStatus,
        jobId);
    return jdbc.queryForObject(
        "select id::text from guides where analysis_job_id = ?", String.class, jobId);
  }

  @Test
  void approvedGuideComesBackStepByStepWithExplanationAndArea() throws Exception {
    String guideId = guideWithStatus("eFzG30avtOI", "APPROVED");

    mockMvc
        .perform(get("/v1/guides/" + guideId).with(member()))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.guideId").value(guideId))
        .andExpect(jsonPath("$.guideVersion").value(1))
        .andExpect(jsonPath("$.youtubeVideoId").value("eFzG30avtOI"))
        .andExpect(jsonPath("$.title").value("베이스부터 립까지"))
        .andExpect(jsonPath("$.channelTitle").value("MAIROR"))
        .andExpect(jsonPath("$.meshVersion").value("v1"))
        .andExpect(jsonPath("$.referenceImageUrl").isEmpty())
        .andExpect(jsonPath("$.steps", hasSize(19)))
        // other 6개(s1~s4·s6·s8)는 제외, 나머지 13개가 따라 하는 단계
        .andExpect(jsonPath("$.stepCount").value(13))
        // 블러셔 2 · 섀도 2 · 라인 2 · 하이라이트 1 · 립 3
        .andExpect(jsonPath("$.previewableStepCount").value(10))
        .andExpect(jsonPath("$.steps[0].stepId").value("s1"))
        .andExpect(jsonPath("$.steps[0].type").value("EXCLUDED"))
        .andExpect(jsonPath("$.steps[0].matchCategory").isEmpty())
        .andExpect(jsonPath("$.steps[0].subSteps[0].status").value("notApplicable"))
        // 파우더(other): 제외 단계여도 설명·제품·도구는 준다
        .andExpect(jsonPath("$.steps[7].stepId").value("s8"))
        .andExpect(jsonPath("$.steps[7].type").value("EXCLUDED"))
        .andExpect(jsonPath("$.steps[7].part").value("other"))
        .andExpect(jsonPath("$.steps[7].partLabel").value("파우더"))
        .andExpect(jsonPath("$.steps[7].tools[0]").value("퍼프"))
        .andExpect(jsonPath("$.steps[7].referenceProduct.name").value("루나 프로 포토 피니셔"))
        .andExpect(jsonPath("$.steps[7].referenceProduct.shadeName").value("02"))
        .andExpect(jsonPath("$.steps[7].referenceProduct.matchStatus").value("UNMATCHED"))
        .andExpect(jsonPath("$.steps[7].referenceProduct.videoConfirmed").value(true))
        .andExpect(jsonPath("$.steps[7].actions[0].text").value("브러시로 가볍게 펴 발라요."))
        .andExpect(jsonPath("$.steps[7].videoRange.startSeconds").value(267.0))
        .andExpect(jsonPath("$.steps[7].videoRange.endSeconds").value(276.0))
        // 마스카라: 영역은 없지만 따라 하는 단계
        .andExpect(jsonPath("$.steps[13].part").value("mascara"))
        .andExpect(jsonPath("$.steps[13].type").value("GUIDE"))
        .andExpect(jsonPath("$.steps[13].previewable").value(false))
        .andExpect(jsonPath("$.steps[13].matchCategory").value("EYE"))
        .andExpect(jsonPath("$.steps[13].subSteps[0].status").value("notApplicable"))
        // 쉐딩은 미리보기 안 됨, 하이라이트는 됨
        .andExpect(jsonPath("$.steps[14].previewable").value(false))
        .andExpect(jsonPath("$.steps[14].matchCategory").value("CHEEK"))
        .andExpect(jsonPath("$.steps[15].previewable").value(true))
        // 립: 영역 상태는 guide-area 그대로(찾음 · 기본 · 실패)
        .andExpect(jsonPath("$.steps[16].subSteps[0].status").value("extracted"))
        .andExpect(jsonPath("$.steps[16].subSteps[0].guideSets[0].region").exists())
        .andExpect(jsonPath("$.steps[16].matchCategory").value("LIP"))
        .andExpect(jsonPath("$.steps[18].type").value("GUIDE"))
        .andExpect(jsonPath("$.steps[18].subSteps[0].status").value("failed"))
        .andExpect(
            jsonPath("$.steps[*].targetColor", everyItem(org.hamcrest.Matchers.nullValue())));
  }

  @Test
  void guidesThatAreNotApprovedOrMissingAre404() throws Exception {
    for (String reviewStatus : List.of("NOT_READY", "PENDING", "REJECTED")) {
      String guideId = guideWithStatus("notOpen" + reviewStatus.substring(0, 4), reviewStatus);
      mockMvc
          .perform(get("/v1/guides/" + guideId).with(member()))
          .andExpect(status().isNotFound())
          .andExpect(jsonPath("$.code").value("NOT_FOUND"));
    }
    mockMvc
        .perform(get("/v1/guides/" + UUID.randomUUID()).with(member()))
        .andExpect(status().isNotFound());
  }

  @Test
  void stepsWithoutExplanationOrAreaStillComeBack() throws Exception {
    String guideId = guideWithStatus("noAreaVid01", "APPROVED");
    jdbc.update(
        "update guides set explanation = '{\"steps\": []}'::jsonb, area = null, mesh_version = null"
            + " where id = ?::uuid",
        guideId);

    mockMvc
        .perform(get("/v1/guides/" + guideId).with(member()))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.meshVersion").isEmpty())
        .andExpect(jsonPath("$.steps[9].actions", hasSize(0)))
        .andExpect(jsonPath("$.steps[9].doneWhen").isEmpty())
        .andExpect(jsonPath("$.steps[9].subSteps", hasSize(0)));
  }

  @Test
  void needsLogin() throws Exception {
    String guideId = guideWithStatus("loginVid001", "APPROVED");

    mockMvc
        .perform(get("/v1/guides/" + guideId))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
  }
}
