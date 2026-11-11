package com.mairor.backend.analysis.worker;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.mairor.backend.analysis.extraction.GuideInput;
import com.mairor.backend.analysis.frames.FrameManifest;
import com.mairor.backend.analysis.service.AiFrameDelivery;
import com.mairor.backend.common.external.ai.AiGuideJobClient;
import com.mairor.backend.common.external.ai.AiProperties;
import com.mairor.backend.common.storage.LocalObjectStorage;
import com.mairor.backend.common.storage.ObjectStorage;
import java.net.URI;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.InOrder;
import tools.jackson.databind.json.JsonMapper;

/**
 * AI 가이드 요청에 레퍼런스 프레임을 싣는지(S15P31A306-410). 로컬 저장소는 {@code file:} 주소라 AI 가 요청 전체를 거절하므로, 설정이 비어 있으면
 * 저장소가 http 주소를 줄 때만 싣는다.
 */
class BuildGuideStepFramesTest {

  @TempDir Path root;

  private static final GuideInput GUIDE_INPUT = new GuideInput("VxAXD6PP76I", 1858.4, List.of());

  private static final FrameManifest FRAMES =
      new FrameManifest(
          "VxAXD6PP76I",
          "job-1",
          new FrameManifest.Source(1920, 1080, 60.0),
          List.of(
              new FrameManifest.Item(
                  38400, 640000, "s1", "videos/VxAXD6PP76I/frames/038400.jpg", 1920, 1080)));

  /** S3 처럼 http 주소를 주는 저장소. */
  private static final ObjectStorage HTTP_STORAGE =
      new ObjectStorage() {
        @Override
        public void download(String key, Path target) {}

        @Override
        public boolean exists(String key) {
          return true;
        }

        @Override
        public void upload(Path source, String key, String contentType) {}

        @Override
        public void delete(String key) {}

        @Override
        public URI presignGet(String key, Duration ttl) {
          return URI.create("https://bucket.s3.amazonaws.com/" + key + "?X-Amz-Signature=x");
        }
      };

  private static AiProperties properties(Boolean sendFrames) {
    return new AiProperties(
        "http://ai:8000",
        "http://api:8080/api",
        Duration.ofSeconds(1),
        Duration.ofSeconds(1),
        Duration.ofHours(24),
        Duration.ofMinutes(60),
        Duration.ofSeconds(60),
        sendFrames);
  }

  private static BuildGuideStep step(ObjectStorage storage, Boolean sendFrames) {
    AiProperties properties = properties(sendFrames);
    return new BuildGuideStep(
        null,
        properties,
        storage,
        null,
        JsonMapper.builder().build(),
        new AiFrameDelivery(properties, storage));
  }

  @Test
  void localStorageSendsNoFramesByDefault() {
    Map<String, Object> request =
        step(new LocalObjectStorage(root), null).request(GUIDE_INPUT, FRAMES);

    assertThat(request).containsKeys("callbackUrl", "progressUrl", "guideInput");
    assertThat(request).doesNotContainKey("frames");
  }

  @Test
  void storageWithHttpUrlsSendsFramesByDefault() {
    Map<String, Object> request = step(HTTP_STORAGE, null).request(GUIDE_INPUT, FRAMES);

    assertThat(request).containsKey("frames");
    assertThat(request.get("frames").toString())
        .contains("https://bucket.s3.amazonaws.com/videos/VxAXD6PP76I/frames/038400.jpg");
  }

  @Test
  void theSettingOverridesTheStorage() {
    assertThat(step(new LocalObjectStorage(root), true).request(GUIDE_INPUT, FRAMES))
        .containsKey("frames");
    assertThat(step(HTTP_STORAGE, false).request(GUIDE_INPUT, FRAMES)).doesNotContainKey("frames");
  }

  @Test
  void theDecisionFollowsTheSettingFirstThenTheStorage() {
    LocalObjectStorage local = new LocalObjectStorage(root);
    assertThat(new AiFrameDelivery(properties(null), local).enabled()).isFalse();
    assertThat(new AiFrameDelivery(properties(null), HTTP_STORAGE).enabled()).isTrue();
    assertThat(new AiFrameDelivery(properties(true), local).enabled()).isTrue();
    assertThat(new AiFrameDelivery(properties(false), HTTP_STORAGE).enabled()).isFalse();
  }

  private AnalysisContext context() {
    AnalysisContext context =
        new AnalysisContext(
            UUID.randomUUID(),
            UUID.randomUUID(),
            "VxAXD6PP76I",
            "videos/VxAXD6PP76I/source.mp4",
            root);
    context.stepsExtracted(GUIDE_INPUT);
    context.framesExtracted(FRAMES);
    return context;
  }

  private BuildGuideStep runnableStep(
      ObjectStorage storage, AiGuideJobClient client, AnalysisJobStore store) {
    AiProperties properties = properties(null);
    return new BuildGuideStep(
        client,
        properties,
        storage,
        store,
        JsonMapper.builder().build(),
        new AiFrameDelivery(properties, storage));
  }

  /** 콜백을 받는 api 의 설정이 달라도 같은 답을 쓰도록, 프레임 없이 맡기는 판단을 요청 전에 가이드에 남긴다. */
  @Test
  void sendingWithoutFramesClearsTheManifestBeforeTheRequest() {
    AiGuideJobClient client = mock(AiGuideJobClient.class);
    AnalysisJobStore store = mock(AnalysisJobStore.class);
    when(client.submit(anyString())).thenReturn("ai-1");
    AnalysisContext context = context();

    runnableStep(new LocalObjectStorage(root), client, store).run(context);

    InOrder order = inOrder(store, client);
    order.verify(store).forgetFramesManifest(context.jobId());
    order.verify(client).submit(argThat(body -> !body.contains("\"frames\"")));
    order.verify(store).awaitAi(context.jobId(), "ai-1");
  }

  @Test
  void sendingWithFramesKeepsTheManifest() {
    AiGuideJobClient client = mock(AiGuideJobClient.class);
    AnalysisJobStore store = mock(AnalysisJobStore.class);
    when(client.submit(anyString())).thenReturn("ai-2");
    AnalysisContext context = context();

    runnableStep(HTTP_STORAGE, client, store).run(context);

    verify(store, never()).forgetFramesManifest(any());
    verify(client).submit(argThat(body -> body.contains("\"frames\"")));
  }
}
