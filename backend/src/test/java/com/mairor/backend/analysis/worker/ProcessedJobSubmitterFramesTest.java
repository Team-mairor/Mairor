package com.mairor.backend.analysis.worker;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.mairor.backend.analysis.service.AiFrameDelivery;
import com.mairor.backend.analysis.service.ProcessorJobService;
import com.mairor.backend.analysis.worker.AnalysisJobStore.ProcessedJob;
import com.mairor.backend.common.external.ai.AiGuideJobClient;
import com.mairor.backend.common.external.ai.AiProperties;
import com.mairor.backend.common.storage.LocalObjectStorage;
import com.mairor.backend.common.storage.StorageProperties;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.json.JsonMapper;

/**
 * 노트북 결과를 AI 에 맡길 때 프레임을 싣는지(S15P31A306-358 · -410). 로컬 저장소처럼 AI 가 받을 수 없는 주소만 주면 프레임을 빼고, 콜백 검사가
 * 영역을 요구하지 않도록 프레임 목록 칸도 남기지 않는다.
 */
class ProcessedJobSubmitterFramesTest {

  private static final String VIDEO = "VxAXD6PP76I";
  private static final String REQUEST_KEY = "videos/VxAXD6PP76I/jobs/j1/guide_job_request.json";

  @TempDir Path storageRoot;
  @TempDir Path workDir;

  private static final String REQUEST =
      "{\"callbackUrl\": \"https://notebook/cb\", \"guideInput\": {\"videoId\": \"VxAXD6PP76I\","
          + " \"durationSeconds\": 600, \"steps\": [{\"stepId\": \"s1\", \"order\": 1, \"makeup\":"
          + " \"lip\"}]}, \"frames\": {\"source\": {\"width\": 1920, \"height\": 1080, \"fps\": 60},"
          + " \"items\": [{\"frameIndex\": 60, \"timestampMs\": 1000, \"stepId\": \"s1\", \"width\":"
          + " 1920, \"height\": 1080, \"key\":"
          + " \"videos/VxAXD6PP76I/jobs/j1/frames/step_01/frame_000060.jpg\"}]}}";

  @Test
  void localStorageSubmitsWithoutFramesAndLeavesNoManifest() throws Exception {
    Path file = storageRoot.resolve(REQUEST_KEY);
    Files.createDirectories(file.getParent());
    Files.writeString(file, REQUEST, StandardCharsets.UTF_8);

    LocalObjectStorage storage = new LocalObjectStorage(storageRoot);
    AiProperties ai =
        new AiProperties(
            "http://ai:8000",
            "http://api:8080/api",
            Duration.ofSeconds(1),
            Duration.ofSeconds(1),
            Duration.ofHours(24),
            Duration.ofMinutes(60),
            Duration.ofSeconds(60),
            null);
    AnalysisJobStore store = mock(AnalysisJobStore.class);
    AiGuideJobClient client = mock(AiGuideJobClient.class);
    UUID jobId = UUID.randomUUID();
    when(store.nextProcessed())
        .thenReturn(Optional.of(new ProcessedJob(jobId, VIDEO, REQUEST_KEY)));
    when(client.submit(anyString())).thenReturn("ai-1");

    ProcessedJobSubmitter submitter =
        new ProcessedJobSubmitter(
            store,
            mock(ProcessorJobService.class),
            storage,
            new StorageProperties(
                StorageProperties.Type.LOCAL,
                new StorageProperties.Local(storageRoot),
                new StorageProperties.S3("mairor-prod-media", "ap-northeast-2")),
            client,
            ai,
            new WorkerProperties(
                Duration.ofSeconds(5),
                workDir,
                "ffprobe",
                Duration.ofSeconds(60),
                "ffmpeg",
                Duration.ofMinutes(30),
                8),
            JsonMapper.builder().build(),
            new AiFrameDelivery(ai, storage));

    assertThat(submitter.submitNext()).isTrue();

    verify(store).saveGuideInput(eq(jobId), anyString());
    verify(store, never()).recordFramesManifest(any(), any());
    verify(client)
        .submit(
            argThat(
                body ->
                    !body.contains("\"frames\"")
                        && body.contains(
                            "http://api:8080/api/v1/internal/ai/guide-jobs/callback")));
    verify(store).awaitAi(jobId, "ai-1");
    verify(store, never()).fail(any(), any(), any());
  }
}
