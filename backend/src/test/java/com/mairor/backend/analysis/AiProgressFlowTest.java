package com.mairor.backend.analysis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.analysis.controller.AiCallbackController;
import com.mairor.backend.analysis.service.AnalysisJobRequest;
import com.mairor.backend.analysis.service.AnalysisJobService;
import com.mairor.backend.analysis.worker.AnalysisJobStore;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

/**
 * AI 진행 알림 → 분석 작업의 진행 숫자. 받을 수 없는 알림도 204 이고 저장하지 않는다. 공유 토큰 없이 부른다(AI 는 헤더를 못 붙인다). 작업은 AI 에 맡긴
 * 상태로 바로 만들어 둔다({@code AiGuideJobFlowTest}와 같다).
 */
@AutoConfigureMockMvc
class AiProgressFlowTest extends AnalysisIntegrationTest {

  private static final String PROGRESS = AiCallbackController.PROGRESS_PATH;
  private static final String AI_JOB = "ai-progress-1";

  /** 실제 AI 형식(`GuideJobProgress`). videoId 가 없다. */
  private static final String WITH_FRAMES =
      """
      {"jobId": "ai-progress-1",
       "explanation": {"done": 19, "total": 19},
       "frames": {"done": 2000, "total": 2000},
       "landmarks": {"done": 840, "total": 2000},
       "area": {"done": 0, "total": 19}}
      """;

  @Autowired private MockMvc mockMvc;
  @Autowired private AnalysisJobService service;
  @Autowired private AnalysisJobStore store;

  /** AI 에 맡긴 작업: 작업 RUNNING · BUILDING_GUIDE · ai_job_id, 가이드는 입력만 있는 NOT_READY. */
  private UUID awaitingJob(String status) {
    UUID jobId =
        service
            .register(
                new AnalysisJobRequest(
                    "eFzG30avtOI", "videos/eFzG30avtOI/source.mp4", "제목", "채널", 600))
            .jobId();
    jdbc.update(
        "update analysis_jobs set status = ?, progress_stage = 'BUILDING_GUIDE',"
            + " started_at = now(), ai_job_id = ? where id = ?",
        status,
        AI_JOB,
        jobId);
    store.saveGuideInput(jobId, "{\"videoId\": \"eFzG30avtOI\", \"steps\": []}");
    return jobId;
  }

  private void send(String body) throws Exception {
    mockMvc
        .perform(post(PROGRESS).contentType(MediaType.APPLICATION_JSON).content(body))
        .andExpect(status().isNoContent());
  }

  private String stored(UUID jobId) {
    return jdbc.queryForObject(
        "select ai_progress::text from analysis_jobs where id = ?", String.class, jobId);
  }

  @Test
  void realAiProgressIsStoredWithoutAToken() throws Exception {
    UUID jobId = awaitingJob("RUNNING");

    send(WITH_FRAMES);

    assertThat(
            jdbc.queryForObject(
                "select (ai_progress -> 'landmarks' ->> 'done') || '/'"
                    + " || (ai_progress -> 'landmarks' ->> 'total') || ':'"
                    + " || (ai_progress -> 'explanation' ->> 'done')"
                    + " from analysis_jobs where id = ?",
                String.class,
                jobId))
        .isEqualTo("840/2000:19");
    assertThat(
            jdbc.queryForObject(
                "select status from analysis_jobs where id = ?", String.class, jobId))
        .as("진행 숫자는 작업 상태를 바꾸지 않는다")
        .isEqualTo("RUNNING");
    assertThat(
            jdbc.queryForObject(
                "select ai_requested_at is not null from analysis_jobs where id = ?",
                Boolean.class,
                jobId))
        .as("맡긴 시각이 빈 작업은 첫 진행 알림 때 시간 초과 기준이 채워진다")
        .isTrue();
  }

  @Test
  void progressOfAJobWithoutFramesIsStored() throws Exception {
    UUID jobId = awaitingJob("RUNNING");

    send(
        """
        {"jobId": "ai-progress-1", "explanation": {"done": 3, "total": 19},
         "frames": null, "landmarks": null, "area": null}
        """);

    assertThat(
            jdbc.queryForObject(
                "select (ai_progress ->> 'explanation') || ':'"
                    + " || jsonb_typeof(ai_progress -> 'frames')"
                    + " from analysis_jobs where id = ?",
                String.class,
                jobId))
        .isEqualTo("{\"done\": 3, \"total\": 19}:null");
  }

  @Test
  void laterProgressReplacesTheEarlierNumbers() throws Exception {
    UUID jobId = awaitingJob("RUNNING");

    send(WITH_FRAMES);
    send(WITH_FRAMES.replace("\"done\": 840", "\"done\": 1990"));

    assertThat(
            jdbc.queryForObject(
                "select ai_progress -> 'landmarks' ->> 'done' from analysis_jobs where id = ?",
                String.class,
                jobId))
        .isEqualTo("1990");
  }

  @Test
  void unknownFieldsAreNotStored() throws Exception {
    UUID jobId = awaitingJob("RUNNING");

    send(
        """
        {"jobId": "ai-progress-1", "extra": 1,
         "explanation": {"done": 3, "total": 19, "note": "x"},
         "frames": null, "landmarks": null, "area": null}
        """);

    assertThat(stored(jobId))
        .doesNotContain("extra")
        .doesNotContain("note")
        .contains("explanation");
  }

  @Test
  void progressForAnUnknownAiJobIsDropped() throws Exception {
    UUID jobId = awaitingJob("RUNNING");

    send(WITH_FRAMES.replace("ai-progress-1", "someone-else"));

    assertThat(stored(jobId)).isNull();
  }

  @Test
  void lateProgressForAFinishedJobIsDropped() throws Exception {
    UUID jobId = awaitingJob("COMPLETED");

    send(WITH_FRAMES);

    assertThat(stored(jobId)).isNull();
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        // JSON 이 아님, 객체가 아님, 빈 본문
        "not json",
        "[1, 2]",
        " ",
        // jobId 없음
        "{\"explanation\": {\"done\": 1, \"total\": 19}}",
        // explanation 없음
        "{\"jobId\": \"ai-progress-1\", \"frames\": null, \"landmarks\": null, \"area\": null}",
        // 정수가 아님
        "{\"jobId\": \"ai-progress-1\", \"explanation\": {\"done\": 1.5, \"total\": 19}}",
        "{\"jobId\": \"ai-progress-1\", \"explanation\": {\"done\": \"1\", \"total\": 19}}",
        // 음수, done > total
        "{\"jobId\": \"ai-progress-1\", \"explanation\": {\"done\": -1, \"total\": 19}}",
        "{\"jobId\": \"ai-progress-1\", \"explanation\": {\"done\": 20, \"total\": 19}}",
        // frames·landmarks·area 중 일부만 있음
        "{\"jobId\": \"ai-progress-1\", \"explanation\": {\"done\": 1, \"total\": 19},"
            + " \"frames\": {\"done\": 1, \"total\": 2}, \"landmarks\": null, \"area\": null}",
        // 영역 쪽 숫자가 틀림
        "{\"jobId\": \"ai-progress-1\", \"explanation\": {\"done\": 1, \"total\": 19},"
            + " \"frames\": {\"done\": 1, \"total\": 2}, \"landmarks\": {\"done\": 3, \"total\":"
            + " 2}, \"area\": {\"done\": 0, \"total\": 19}}"
      })
  void invalidProgressIsDroppedWith204(String body) throws Exception {
    UUID jobId = awaitingJob("RUNNING");

    send(body);

    assertThat(stored(jobId)).isNull();
    assertThat(
            jdbc.queryForObject(
                "select status from analysis_jobs where id = ?", String.class, jobId))
        .isEqualTo("RUNNING");
  }
}
