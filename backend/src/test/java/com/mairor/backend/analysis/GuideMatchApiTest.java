package com.mairor.backend.analysis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.analysis.service.AnalysisJobRequest;
import com.mairor.backend.analysis.service.AnalysisJobService;
import com.mairor.backend.analysis.worker.AnalysisJobStore;
import com.mairor.backend.pouch.repository.PouchVersionRepository;
import com.mairor.backend.users.support.AuthenticatedUser;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.core.io.ClassPathResource;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import tools.jackson.databind.json.JsonMapper;

/** 매칭 생성·조회 API의 실제 DB 트랜잭션, 응답, 소유권을 확인한다. */
@AutoConfigureMockMvc
class GuideMatchApiTest extends AnalysisIntegrationTest {

  private static final String PATH = "/v1/users/me/guide-matches";

  @Autowired private MockMvc mockMvc;
  @Autowired private AnalysisJobService analysisJobs;
  @Autowired private AnalysisJobStore analysisStore;
  @MockitoSpyBean private PouchVersionRepository pouchVersions;

  private UUID userId;
  private UUID otherUserId;

  @BeforeEach
  void setUp() {
    userId = UUID.randomUUID();
    otherUserId = UUID.randomUUID();
    insertUser(userId);
    insertUser(otherUserId);
  }

  @AfterEach
  void cleanUp() {
    jdbc.update("delete from guide_matches where user_id in (?, ?)", userId, otherUserId);
    jdbc.update("delete from users where id in (?, ?)", userId, otherUserId);
  }

  @Test
  void createAndGetUseRepeatableReadAndOtherMemberCannotReadTheSnapshot() throws Exception {
    UUID guideId = approvedGuide();
    doAnswer(
            invocation -> {
              assertThat(TransactionSynchronizationManager.getCurrentTransactionIsolationLevel())
                  .isEqualTo(TransactionDefinition.ISOLATION_REPEATABLE_READ);
              return invocation.callRealMethod();
            })
        .when(pouchVersions)
        .findByUserId(userId);

    MvcResult created =
        mockMvc
            .perform(
                post(PATH)
                    .with(asMember(userId))
                    .with(csrf())
                    .contentType("application/json")
                    .content("{\"guideId\":\"" + guideId + "\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.guideId").value(guideId.toString()))
            .andExpect(jsonPath("$.pouchVersion").value(0))
            .andReturn();

    String matchId =
        JsonMapper.builder()
            .build()
            .readTree(created.getResponse().getContentAsString())
            .path("matchId")
            .asString();

    mockMvc
        .perform(get(PATH + "/" + matchId).with(asMember(userId)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.matchId").value(matchId))
        .andExpect(jsonPath("$.stale").value(false));

    mockMvc
        .perform(get(PATH + "/" + matchId).with(asMember(otherUserId)))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOT_FOUND"));

    verify(pouchVersions, times(2)).findByUserId(userId);
  }

  private void insertUser(UUID id) {
    jdbc.update(
        "insert into users (id, email, provider, created_at, updated_at)"
            + " values (?, ?, 'LOCAL', now(), now())",
        id,
        id + "@example.com");
  }

  private UUID approvedGuide() throws IOException {
    String youtubeVideoId = "GM" + UUID.randomUUID().toString().replace("-", "").substring(0, 9);
    UUID jobId =
        analysisJobs
            .register(
                new AnalysisJobRequest(
                    youtubeVideoId,
                    "videos/" + youtubeVideoId + "/source.mp4",
                    "Guide match test",
                    "MAIROR",
                    525))
            .jobId();
    analysisStore.saveGuideInput(
        jobId,
        new ClassPathResource("analysis/guide-input-eFzG30avtOI.json")
            .getContentAsString(StandardCharsets.UTF_8));
    jdbc.update("update guides set review_status = 'APPROVED' where analysis_job_id = ?", jobId);
    return jdbc.queryForObject(
        "select id from guides where analysis_job_id = ?", UUID.class, jobId);
  }

  private static RequestPostProcessor asMember(UUID id) {
    return authentication(
        UsernamePasswordAuthenticationToken.authenticated(
            new AuthenticatedUser(id, id + "@example.com"),
            null,
            List.of(new SimpleGrantedAuthority("ROLE_USER"))));
  }
}
