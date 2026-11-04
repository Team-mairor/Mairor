package com.mairor.backend.analysis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.mairor.backend.analysis.controller.AiCallbackController;
import com.mairor.backend.analysis.dto.request.AiGuideJobCallbackRequest;
import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.entity.ProgressStage;
import com.mairor.backend.analysis.extraction.GuideInputSchema;
import com.mairor.backend.analysis.frames.FrameExtractionException;
import com.mairor.backend.analysis.frames.FrameExtractor;
import com.mairor.backend.analysis.frames.FramePlan;
import com.mairor.backend.analysis.repository.AnalysisJobRepository;
import com.mairor.backend.analysis.service.AiResultService;
import com.mairor.backend.analysis.service.AnalysisJobReceipt;
import com.mairor.backend.analysis.service.AnalysisJobRequest;
import com.mairor.backend.analysis.service.AnalysisJobService;
import com.mairor.backend.analysis.service.ReceiptType;
import com.mairor.backend.analysis.worker.AnalysisJobRunner;
import com.mairor.backend.analysis.worker.AnalysisJobStore;
import com.mairor.backend.analysis.worker.Ffprobe;
import com.mairor.backend.analysis.worker.FfprobeException;
import com.mairor.backend.analysis.worker.VideoProbe;
import com.mairor.backend.common.external.ai.AiGuideJobClient;
import com.mairor.backend.common.external.ai.AiServerException;
import com.mairor.backend.common.external.llm.LlmClient;
import com.mairor.backend.common.external.llm.LlmException;
import com.mairor.backend.common.external.llm.LlmResult;
import com.mairor.backend.videos.repository.VideoRepository;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import tools.jackson.databind.json.JsonMapper;

/**
 * 작업 접수 → worker 실행의 흐름. 실제 DB(스키마 SQL)와 로컬 저장소를 쓰고 ffprobe · Gemini(LlmClient) · ffmpeg 추출기만 가짜로
 * 바꾼다(진짜 ffmpeg 는 {@code FrameExtractorTest}). worker 스케줄러는 {@code worker} 프로파일이 아니라 뜨지 않으므로 실행기를
 * 직접 부른다.
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
  @MockitoBean private FrameExtractor frameExtractor;
  @MockitoBean private AiGuideJobClient ai;
  @Autowired private AiResultService aiResults;

  /** 가짜 AI 서버: 요청을 받으면 작업 ID 를 돌려준다(영상마다 다르게). */
  private void aiAccepts() {
    doAnswer(call -> "ai-" + UUID.randomUUID()).when(ai).submit(any());
  }

  /** AI 콜백이 온 것처럼 결과를 반영한다. */
  private void aiCompletes(UUID jobId) {
    String aiJobId = jobs.findById(jobId).orElseThrow().getAiJobId();
    var json = JsonMapper.builder().build();
    aiResults.apply(
        new AiGuideJobCallbackRequest(
            aiJobId,
            "VxAXD6PP76I",
            "COMPLETED",
            json.readTree("{\"steps\": [{\"stepId\": \"s1\", \"order\": 1, \"actions\": []}]}"),
            null,
            null));
  }

  /** 가짜 추출기: 계획의 후보만큼 작은 파일을 만든다(ffmpeg 가 다 뽑은 것처럼). */
  private void framesExtractNormally() {
    doAnswer(
            call -> {
              FramePlan plan = call.getArgument(1);
              Path outDir = call.getArgument(2);
              Files.createDirectories(outDir);
              List<Path> files = new ArrayList<>();
              for (int i = 1; i <= plan.candidates().size(); i++) {
                files.add(Files.writeString(outDir.resolve(String.format("%06d.jpg", i)), "jpg"));
              }
              return files;
            })
        .when(frameExtractor)
        .extract(any(), any(), any());
  }

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
    framesExtractNormally();
    aiAccepts();
    AnalysisJobReceipt receipt = service.register(request("VxAXD6PP76I"));

    assertThat(runner.runNext()).isTrue();

    AnalysisJob job = jobs.findById(receipt.jobId()).orElseThrow();
    assertThat(job.getStatus()).as("AI 콜백을 기다린다").isEqualTo(AnalysisStatus.RUNNING);
    assertThat(job.getProgressStage()).isEqualTo(ProgressStage.BUILDING_GUIDE);
    assertThat(job.getAiJobId()).startsWith("ai-");
    assertThat(job.getStartedAt()).isNotNull();
    assertThat(store.requeueRunning()).as("AI 를 기다리는 작업은 재시작 때 되돌리지 않는다").isZero();

    ArgumentCaptor<String> body = ArgumentCaptor.forClass(String.class);
    verify(ai).submit(body.capture());
    assertThat(GuideJobSchemas.requestViolations(body.getValue())).isEmpty();
    assertThat(body.getValue())
        .contains(
            "\"callbackUrl\":\"http://localhost:8080/api/v1/internal/ai/guide-jobs/callback\"")
        .as("진행 알림 주소는 AI 가 부를 BE 의 진행 알림 API 다")
        .contains(
            "\"progressUrl\":\"http://localhost:8080/api"
                + AiCallbackController.PROGRESS_PATH
                + "\"")
        .contains("\"frames\":{\"source\":{\"width\":1920,\"height\":1080,\"fps\":60.0}")
        .contains("\"frameIndex\":38400,\"timestampMs\":640000,\"stepId\":\"s1\",\"url\":\"file:");

    aiCompletes(receipt.jobId());
    job = jobs.findById(receipt.jobId()).orElseThrow();
    assertThat(job.getStatus()).isEqualTo(AnalysisStatus.COMPLETED);
    assertThat(job.getProgressStage()).isEqualTo(ProgressStage.DONE);
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
        .as("AI 콜백 뒤 검수 대기")
        .isEqualTo("PENDING:1");
    assertThat(
            jdbc.queryForObject(
                "select provider || ':' || status || ':' || input_tokens || ':' || purpose"
                    + " from llm_calls where analysis_job_id = ?",
                String.class,
                receipt.jobId()))
        .isEqualTo("GMS:SUCCEEDED:540000:STEP_EXTRACTION");

    String manifestKey =
        jdbc.queryForObject(
            "select frames_manifest_key from guides where analysis_job_id = ?",
            String.class,
            receipt.jobId());
    assertThat(manifestKey)
        .isEqualTo("videos/VxAXD6PP76I/jobs/" + receipt.jobId() + "/frames.json");
    String manifest = readObject(manifestKey);
    assertThat(manifest)
        .contains("\"source\":{\"width\":1920,\"height\":1080,\"fps\":60.0}")
        .contains(
            "{\"frameIndex\":0,\"timestampMs\":0,\"stepId\":null,"
                + "\"key\":\"videos/VxAXD6PP76I/frames/000000.jpg\",\"width\":1920,\"height\":1080}")
        .as("10:40(640초) 단계 시작 = 38400번 프레임")
        .contains("{\"frameIndex\":38400,\"timestampMs\":640000,\"stepId\":\"s1\"");
    assertThat(STORAGE_ROOT.resolve("videos/VxAXD6PP76I/frames/038400.jpg")).exists();
  }

  @Test
  void aiServerThatDoesNotAcceptFailsAsRetryable() {
    putObject("videos/aiIsDown01/source.mp4");
    when(ffprobe.probe(any())).thenReturn(PROBE);
    when(llm.generate(any())).thenReturn(answer(GEMINI_STEPS));
    framesExtractNormally();
    when(ai.submit(any())).thenThrow(new AiServerException("AI 서버에 연결하지 못했습니다", null, null));
    AnalysisJobReceipt receipt = service.register(request("aiIsDown01"));

    runner.runNext();

    AnalysisJob job = jobs.findById(receipt.jobId()).orElseThrow();
    assertThat(job.getStatus()).isEqualTo(AnalysisStatus.FAILED);
    assertThat(job.getProgressStage()).isEqualTo(ProgressStage.BUILDING_GUIDE);
    assertThat(job.getFailureCode()).isEqualTo("AI_UNAVAILABLE");
    assertThat(job.isRetryable()).isTrue();
    assertThat(job.getAiJobId()).isNull();
  }

  /**
   * AI 가 요청을 거절하면(형식 400, 너무 큼 413 등) 같은 입력으로 다시 해도 같은 결과라 재시도 불가로 끝낸다(서연 후속 요청 5번). 408 · 429 ·
   * 5xx 는 잠깐의 문제라 지금처럼 재시도 가능.
   */
  @Test
  void aiServerThatRejectsTheRequestFailsWithoutRetry() {
    record Case(String videoId, int status, String failureCode, boolean retryable) {}
    List<Case> cases =
        List.of(
            new Case("aiReject400", 400, "AI_REQUEST_REJECTED", false),
            new Case("aiReject413", 413, "AI_REQUEST_REJECTED", false),
            new Case("aiBusy00408", 408, "AI_UNAVAILABLE", true),
            new Case("aiBusy00429", 429, "AI_UNAVAILABLE", true),
            new Case("aiDown00503", 503, "AI_UNAVAILABLE", true));
    when(ffprobe.probe(any())).thenReturn(PROBE);
    when(llm.generate(any())).thenReturn(answer(GEMINI_STEPS));
    framesExtractNormally();

    for (Case c : cases) {
      putObject("videos/" + c.videoId() + "/source.mp4");
      doThrow(
              new AiServerException(
                  "AI 서버가 요청을 받지 않았습니다(HTTP " + c.status() + ")", c.status(), null))
          .when(ai)
          .submit(any());
      AnalysisJobReceipt receipt = service.register(request(c.videoId()));

      runner.runNext();

      AnalysisJob job = jobs.findById(receipt.jobId()).orElseThrow();
      assertThat(job.getStatus()).as("HTTP %d", c.status()).isEqualTo(AnalysisStatus.FAILED);
      assertThat(job.getFailureCode()).as("HTTP %d", c.status()).isEqualTo(c.failureCode());
      assertThat(job.isRetryable()).as("HTTP %d", c.status()).isEqualTo(c.retryable());
    }
  }

  @Test
  void frameExtractionFailureStopsAtSegmentingWithoutRetry() {
    putObject("videos/noFrames001/source.mp4");
    when(ffprobe.probe(any())).thenReturn(PROBE);
    when(llm.generate(any())).thenReturn(answer(GEMINI_STEPS));
    when(frameExtractor.extract(any(), any(), any()))
        .thenThrow(new FrameExtractionException("ffmpeg 가 실패했습니다(종료 코드 1): broken", null));
    AnalysisJobReceipt receipt = service.register(request("noFrames001"));

    runner.runNext();

    AnalysisJob job = jobs.findById(receipt.jobId()).orElseThrow();
    assertThat(job.getProgressStage()).isEqualTo(ProgressStage.SEGMENTING);
    assertThat(job.getFailureCode()).isEqualTo("FRAME_EXTRACTION_FAILED");
    assertThat(job.isRetryable()).isFalse();
  }

  private static String readObject(String key) {
    try {
      return Files.readString(STORAGE_ROOT.resolve(key));
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
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
    framesExtractNormally();
    aiAccepts();
    AnalysisJobReceipt first = service.register(request("twiceVideo1"));
    runner.runNext();
    aiCompletes(first.jobId());
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
    framesExtractNormally();
    aiAccepts();
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
