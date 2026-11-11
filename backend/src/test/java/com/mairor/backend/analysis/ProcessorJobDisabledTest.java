package com.mairor.backend.analysis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.analysis.service.AnalysisJobRequest;
import com.mairor.backend.analysis.service.AnalysisJobService;
import com.mairor.backend.analysis.service.ProcessorJobService;
import com.mairor.backend.analysis.worker.AnalysisJobStore;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

/** 노트북 연결 모드가 꺼져 있으면(기본, S15P31A306-357) 노트북은 작업을 받지 못하고 worker 가 지금처럼 집는다. */
@AutoConfigureMockMvc
@TestPropertySource(properties = "app.processor.token=" + ProcessorJobDisabledTest.PROCESSOR_TOKEN)
class ProcessorJobDisabledTest extends AnalysisIntegrationTest {

  static final String PROCESSOR_TOKEN = "test-processor-token";

  @Autowired private MockMvc mockMvc;
  @Autowired private AnalysisJobService service;
  @Autowired private AnalysisJobStore store;
  @Autowired private ProcessorJobService processorJobs;

  /** 연결 모드를 끄고 다시 뜨면, 노트북이 가져갔던 작업을 worker 가 다시 처리하도록 대기열로 되돌린다(MR !125 리뷰). */
  @Test
  void processorJobsGoBackToTheQueueWhenTheModeIsOff() {
    UUID leased =
        service
            .register(
                new AnalysisJobRequest(
                    "disabled003", "videos/disabled003/source.mp4", "제목", "채널", 600))
            .jobId();
    UUID handedOver =
        service
            .register(
                new AnalysisJobRequest(
                    "disabled004", "videos/disabled004/source.mp4", "제목", "채널", 600))
            .jobId();
    jdbc.update(
        "update analysis_jobs set status = 'RUNNING', progress_stage = 'LOADING_VIDEO', started_at = now(),"
            + " processor_lease_until = now() + interval '10 minutes', processor_claims = 1 where id = ?",
        leased);
    jdbc.update(
        "update analysis_jobs set status = 'RUNNING', progress_stage = 'BUILDING_GUIDE', started_at = now(),"
            + " processor_claims = 1, processor_request_key = 'videos/disabled004/jobs/x/r.json' where id = ?",
        handedOver);

    assertThat(store.requeueRunning()).isEqualTo(1);

    assertThat(
            jdbc.queryForObject(
                "select status || ':' || (processor_lease_until is null) from analysis_jobs where id = ?",
                String.class,
                leased))
        .isEqualTo("PENDING:true");
    assertThat(
            jdbc.queryForObject(
                "select status from analysis_jobs where id = ?", String.class, handedOver))
        .as("노트북이 끝낸 작업은 AI 에 맡길 차례라 그대로")
        .isEqualTo("RUNNING");
  }

  @Test
  void claimIsEmptyAndTheWorkerKeepsTakingJobs() throws Exception {
    service.register(
        new AnalysisJobRequest("disabled001", "videos/disabled001/source.mp4", "제목", "채널", 600));

    mockMvc
        .perform(
            post("/v1/internal/processor/jobs/claim").header("X-Processor-Token", PROCESSOR_TOKEN))
        .andExpect(status().isNoContent());
    assertThat(store.claimNext(WORK_ROOT)).isPresent();
  }

  @Test
  void waitingJobsAreNotTimedOut() {
    service.register(
        new AnalysisJobRequest("disabled002", "videos/disabled002/source.mp4", "제목", "채널", 600));
    jdbc.update("update analysis_jobs set created_at = now() - interval '2 hours'");

    assertThat(processorJobs.expireWaiting()).as("worker 가 처리하는 대기 작업은 노트북 시간 초과 대상이 아니다").isZero();
  }
}
