package com.mairor.backend.analysis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.entity.ProgressStage;
import com.mairor.backend.analysis.extraction.GuideInputSchema;
import com.mairor.backend.analysis.repository.AnalysisJobRepository;
import com.mairor.backend.analysis.service.AnalysisJobReceipt;
import com.mairor.backend.analysis.service.AnalysisJobRequest;
import com.mairor.backend.analysis.service.AnalysisJobService;
import com.mairor.backend.analysis.service.ReceiptType;
import com.mairor.backend.analysis.worker.AnalysisJobRunner;
import com.mairor.backend.analysis.worker.AnalysisJobStore;
import com.mairor.backend.analysis.worker.Ffprobe;
import com.mairor.backend.analysis.worker.FfprobeException;
import com.mairor.backend.analysis.worker.VideoProbe;
import com.mairor.backend.common.external.llm.LlmClient;
import com.mairor.backend.common.external.llm.LlmException;
import com.mairor.backend.common.external.llm.LlmResult;
import com.mairor.backend.videos.repository.VideoRepository;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

/**
 * 작업 접수 → worker 실행의 흐름. 실제 DB(스키마 SQL)와 로컬 저장소를 쓰고 ffprobe 와 Gemini(LlmClient)만 가짜로 바꾼다. worker
 * 스케줄러는 {@code worker} 프로파일이 아니라 뜨지 않으므로 실행기를 직접 부른다.
 */
class AnalysisWorkerFlowTest extends AnalysisIntegrationTest {

  private static final VideoProbe PROBE = new VideoProbe(1920, 1080, 60.0, 1858.2);

  @Autowired private AnalysisJobService service;
  @Autowired private AnalysisJobRunner runner;
  @Autowired private AnalysisJobStore store;
  @Autowired private AnalysisJobRepository jobs;
  @Autowired private VideoRepository videos;
  @MockitoBean private Ffprobe ffprobe;
  @MockitoBean private LlmClient llm;

  /** 단계 하나짜리 Gemini 답. 끝 시각(30:59)이 영상 길이(1858.2초)를 조금 넘어 길이로 잘린다. */
  private static final String GEMINI_STEPS =
      """
      {"steps": [{"order": 1, "makeup": "eyeshadow", "partLabel": "아이섀도", "startTime": "10:40",
        "endTime": "30:59", "summary": "윗눈두덩에 바른다",
        "product": {"brand": "롬앤", "name": "베러 댄 팔레트", "shade": null,
                    "palette": {"color": {"value": "가장 연한 베이지", "source": "voice", "at": "10:41"}}},
        "facts": {"area": {"value": "윗눈두덩 전체", "source": "voice", "at": "10:42"}}}]}
      """;

  private static LlmResult answer(String text) {
    return new LlmResult("GMS", "gemini-2.5-flash", text, 540_000, 20_000, 1);
  }

  private static AnalysisJobRequest request(String youtubeVideoId) {
    return new AnalysisJobRequest(
        youtubeVideoId, "videos/" + youtubeVideoId + "/source.mp4", "제목", "채널", 600);
  }

  @Test
  void loadsTheVideoAndCompletes() {
    putObject("videos/VxAXD6PP76I/source.mp4");
    when(ffprobe.probe(any())).thenReturn(PROBE);
    when(llm.generate(any())).thenReturn(answer(GEMINI_STEPS));
    AnalysisJobReceipt receipt = service.register(request("VxAXD6PP76I"));

    assertThat(runner.runNext()).isTrue();

    AnalysisJob job = jobs.findById(receipt.jobId()).orElseThrow();
    assertThat(job.getStatus()).isEqualTo(AnalysisStatus.COMPLETED);
    assertThat(job.getProgressStage()).isEqualTo(ProgressStage.DONE);
    assertThat(job.getStartedAt()).isNotNull();
    var video = videos.findByYoutubeVideoId("VxAXD6PP76I").orElseThrow();
    assertThat(video.getSourceWidth()).isEqualTo(1920);
    assertThat(video.getSourceFps()).isEqualTo(60.0);
    assertThat(video.getSourceDurationSeconds()).isEqualTo(1858.2);
    assertThat(runner.runNext()).as("대기 작업이 더 없다").isFalse();

    String guideInput =
        jdbc.queryForObject(
            "select guide_input::text from guides where analysis_job_id = ?",
            String.class,
            receipt.jobId());
    assertThat(GuideInputSchema.violations(guideInput)).isEmpty();
    assertThat(
            jdbc.queryForObject(
                "select (guide_input #>> '{steps,0,stepId}') || ':' || (guide_input #>> '{steps,0,endSeconds}')"
                    + " from guides where analysis_job_id = ?",
                String.class,
                receipt.jobId()))
        .as("끝이 영상 길이로 잘린다")
        .isEqualTo("s1:1858.2");
    assertThat(
            jdbc.queryForObject(
                "select review_status || ':' || version from guides where analysis_job_id = ?",
                String.class,
                receipt.jobId()))
        .isEqualTo("NOT_READY:1");
    assertThat(
            jdbc.queryForObject(
                "select provider || ':' || status || ':' || input_tokens || ':' || purpose"
                    + " from llm_calls where analysis_job_id = ?",
                String.class,
                receipt.jobId()))
        .isEqualTo("GMS:SUCCEEDED:540000:STEP_EXTRACTION");
  }

  @Test
  void llmFailureIsRecordedAndRetryable() {
    putObject("videos/llmDownVid1/source.mp4");
    when(ffprobe.probe(any())).thenReturn(PROBE);
    when(llm.generate(any()))
        .thenThrow(
            new LlmException(
                LlmException.Kind.UNAVAILABLE,
                "Gemini 가 일시적으로 응답하지 않습니다(HTTP 503).",
                503,
                "GMS",
                "gemini-2.5-flash",
                null));
    AnalysisJobReceipt receipt = service.register(request("llmDownVid1"));

    runner.runNext();

    AnalysisJob job = jobs.findById(receipt.jobId()).orElseThrow();
    assertThat(job.getStatus()).isEqualTo(AnalysisStatus.FAILED);
    assertThat(job.getProgressStage()).isEqualTo(ProgressStage.EXTRACTING_STEPS);
    assertThat(job.getFailureCode()).isEqualTo("LLM_UNAVAILABLE");
    assertThat(job.isRetryable()).isTrue();
    assertThat(
            jdbc.queryForObject(
                "select status || ':' || error_code from llm_calls where analysis_job_id = ?",
                String.class,
                receipt.jobId()))
        .isEqualTo("FAILED:UNAVAILABLE_503");
    assertThat(jdbc.queryForObject("select count(*) from guides", Integer.class)).isZero();
  }

  @Test
  void answerThatIsNotJsonIsAnInvalidResponse() {
    putObject("videos/badAnswer01/source.mp4");
    when(ffprobe.probe(any())).thenReturn(PROBE);
    when(llm.generate(any())).thenReturn(answer("메이크업 단계는 다음과 같습니다"));
    AnalysisJobReceipt receipt = service.register(request("badAnswer01"));

    runner.runNext();

    AnalysisJob job = jobs.findById(receipt.jobId()).orElseThrow();
    assertThat(job.getFailureCode()).isEqualTo("LLM_INVALID_RESPONSE");
    assertThat(job.isRetryable()).isTrue();
  }

  @Test
  void videoWithoutUsableStepsFailsWithoutRetry() {
    putObject("videos/notMakeup01/source.mp4");
    when(ffprobe.probe(any())).thenReturn(PROBE);
    when(llm.generate(any())).thenReturn(answer("{\"steps\": []}"));
    AnalysisJobReceipt receipt = service.register(request("notMakeup01"));

    runner.runNext();

    AnalysisJob job = jobs.findById(receipt.jobId()).orElseThrow();
    assertThat(job.getFailureCode()).isEqualTo("NO_VALID_STEPS");
    assertThat(job.isRetryable()).isFalse();
  }

  @Test
  void nextAnalysisOfTheSameVideoGetsTheNextGuideVersion() {
    putObject("videos/twiceVideo1/source.mp4");
    when(ffprobe.probe(any())).thenReturn(PROBE);
    when(llm.generate(any())).thenReturn(answer(GEMINI_STEPS));
    service.register(request("twiceVideo1"));
    runner.runNext();
    AnalysisJobReceipt second = service.register(request("twiceVideo1"));

    runner.runNext();

    assertThat(
            jdbc.queryForObject(
                "select version from guides where analysis_job_id = ?",
                Integer.class,
                second.jobId()))
        .isEqualTo(2);
  }

  @Test
  void rerunningAJobReplacesItsGuideInput() {
    putObject("videos/rerunVideo1/source.mp4");
    when(ffprobe.probe(any())).thenReturn(PROBE);
    when(llm.generate(any())).thenReturn(answer(GEMINI_STEPS));
    AnalysisJobReceipt receipt = service.register(request("rerunVideo1"));
    runner.runNext();

    store.saveGuideInput(receipt.jobId(), "{\"videoId\": \"rerunVideo1\", \"steps\": []}");

    assertThat(jdbc.queryForObject("select count(*) from guides", Integer.class)).isEqualTo(1);
    assertThat(
            jdbc.queryForObject(
                "select guide_input ->> 'videoId' from guides where analysis_job_id = ?",
                String.class,
                receipt.jobId()))
        .isEqualTo("rerunVideo1");
  }

  @Test
  void missingSourceFileFailsWithoutRetry() {
    AnalysisJobReceipt receipt = service.register(request("noFileHere1"));

    runner.runNext();

    AnalysisJob job = jobs.findById(receipt.jobId()).orElseThrow();
    assertThat(job.getStatus()).isEqualTo(AnalysisStatus.FAILED);
    assertThat(job.getProgressStage()).isEqualTo(ProgressStage.LOADING_VIDEO);
    assertThat(job.getFailureCode()).isEqualTo("SOURCE_NOT_FOUND");
    assertThat(job.isRetryable()).isFalse();
  }

  @Test
  void unreadableVideoFailsWithoutRetry() {
    putObject("videos/brokenVideo/source.mp4");
    when(ffprobe.probe(any())).thenThrow(new FfprobeException("영상 스트림이 없습니다."));
    AnalysisJobReceipt receipt = service.register(request("brokenVideo"));

    runner.runNext();

    AnalysisJob job = jobs.findById(receipt.jobId()).orElseThrow();
    assertThat(job.getFailureCode()).isEqualTo("SOURCE_UNREADABLE");
    assertThat(job.getFailureMessage()).contains("영상 스트림이 없습니다");
    assertThat(job.isRetryable()).isFalse();
  }

  @Test
  void unexpectedErrorFailsAsRetryableInternalError() {
    putObject("videos/explodeVid1/source.mp4");
    when(ffprobe.probe(any())).thenThrow(new IllegalStateException("boom"));
    AnalysisJobReceipt receipt = service.register(request("explodeVid1"));

    runner.runNext();

    AnalysisJob job = jobs.findById(receipt.jobId()).orElseThrow();
    assertThat(job.getFailureCode()).isEqualTo("INTERNAL_ERROR");
    assertThat(job.isRetryable()).isTrue();
  }

  @Test
  void afterAFailureTheSameVideoCanBeRegisteredAgain() {
    AnalysisJobReceipt first = service.register(request("retryVideo1"));
    runner.runNext();

    AnalysisJobReceipt second = service.register(request("retryVideo1"));

    assertThat(second.receiptType()).isEqualTo(ReceiptType.NEW_JOB);
    assertThat(second.jobId()).isNotEqualTo(first.jobId());
  }

  @Test
  void runningJobLeftByACrashGoesBackToPending() {
    AnalysisJobReceipt receipt = service.register(request("crashedVid1"));
    jdbc.update(
        "update analysis_jobs set status = 'RUNNING', progress_stage = 'LOADING_VIDEO',"
            + " started_at = now() where id = ?",
        receipt.jobId());

    assertThat(store.requeueRunning()).isEqualTo(1);

    AnalysisJob job = jobs.findById(receipt.jobId()).orElseThrow();
    assertThat(job.getStatus()).isEqualTo(AnalysisStatus.PENDING);
    assertThat(job.getStartedAt()).isNull();
  }

  @Test
  void concurrentRegistrationsOfTheSameVideoCreateOneJob() throws Exception {
    int threads = 4;
    ExecutorService pool = Executors.newFixedThreadPool(threads);
    try {
      Callable<AnalysisJobReceipt> task = () -> service.register(request("sameVideo01"));
      List<Future<AnalysisJobReceipt>> futures = pool.invokeAll(List.of(task, task, task, task));

      List<AnalysisJobReceipt> receipts =
          futures.stream()
              .map(
                  f -> {
                    try {
                      return f.get();
                    } catch (Exception e) {
                      throw new IllegalStateException(e);
                    }
                  })
              .toList();

      assertThat(receipts)
          .extracting(AnalysisJobReceipt::jobId)
          .containsOnly(receipts.get(0).jobId());
      assertThat(receipts).filteredOn(r -> r.receiptType() == ReceiptType.NEW_JOB).hasSize(1);
      assertThat(jdbc.queryForObject("select count(*) from analysis_jobs", Integer.class))
          .isEqualTo(1);
      assertThat(jdbc.queryForObject("select count(*) from videos", Integer.class)).isEqualTo(1);
    } finally {
      pool.shutdownNow();
    }
  }

  @Test
  void unknownJobIdHasNoRow() {
    assertThat(jobs.findById(UUID.randomUUID())).isEmpty();
  }
}
