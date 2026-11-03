package com.mairor.backend.analysis.worker;

import com.mairor.backend.analysis.entity.AnalysisFailureCode;
import com.mairor.backend.analysis.entity.ProgressStage;
import com.mairor.backend.analysis.extraction.GuideInput;
import com.mairor.backend.analysis.frames.FrameExtractionException;
import com.mairor.backend.analysis.frames.FrameExtractor;
import com.mairor.backend.analysis.frames.FrameManifest;
import com.mairor.backend.analysis.frames.FramePlan;
import com.mairor.backend.analysis.frames.PlannedFrame;
import com.mairor.backend.common.storage.ObjectStorage;
import com.mairor.backend.common.storage.StorageException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

/**
 * 프레임 추출(SEGMENTING): 단계 추출이 정한 단계 구간을 따라 영상 전체에서 프레임을 뽑아 저장소에 올리고, 프레임 목록({@code frames.json})을
 * 작업의 가이드에 연결한다(현수 레퍼런스 프레임 요청).
 *
 * <p>그림 키는 {@code videos/{videoId}/frames/{frameIndex:06d}.jpg}다. 같은 영상이면 번호가 같은 그림이라 다시 분석해도 덮어써도
 * 된다. 목록은 단계가 작업마다 달라 {@code videos/{videoId}/jobs/{jobId}/frames.json}에 둔다. 올린 그림은 바로 지워 작업 폴더가
 * 커지지 않게 한다.
 */
@Component
class SegmentFramesStep implements AnalysisStepHandler {

  private static final Logger log = LoggerFactory.getLogger(SegmentFramesStep.class);

  private final FrameExtractor extractor;
  private final ObjectStorage storage;
  private final AnalysisJobStore store;
  private final WorkerProperties properties;
  private final ObjectMapper objectMapper;

  SegmentFramesStep(
      FrameExtractor extractor,
      ObjectStorage storage,
      AnalysisJobStore store,
      WorkerProperties properties,
      ObjectMapper objectMapper) {
    this.extractor = extractor;
    this.storage = storage;
    this.store = store;
    this.properties = properties;
    this.objectMapper = objectMapper;
  }

  @Override
  public ProgressStage stage() {
    return ProgressStage.SEGMENTING;
  }

  @Override
  public void run(AnalysisContext context) {
    VideoProbe probe = context.probe();
    GuideInput guideInput = context.guideInput();
    if (probe == null || guideInput == null) {
      throw new IllegalStateException("영상 불러오기·단계 추출 전에는 프레임을 뽑을 수 없습니다.");
    }
    String videoId = context.youtubeVideoId();
    FramePlan plan = FramePlan.of(probe.fps(), probe.durationSeconds(), guideInput.steps());

    long started = System.nanoTime();
    List<Path> files;
    List<PlannedFrame> frames;
    try {
      files = extractor.extract(context.sourceFile(), plan, context.workDir().resolve("frames"));
      frames = plan.truncate(files.size());
    } catch (FrameExtractionException | IllegalStateException e) {
      throw new AnalysisStepException(
          AnalysisFailureCode.FRAME_EXTRACTION_FAILED, e.getMessage(), e);
    }
    long extractedMs = millisSince(started);
    long bytes = totalBytes(files);

    started = System.nanoTime();
    List<FrameManifest.Item> items = new ArrayList<>(frames.size());
    for (PlannedFrame frame : frames) {
      items.add(
          new FrameManifest.Item(
              frame.frameIndex(),
              frame.timestampMs(),
              frame.stepId(),
              frameKey(videoId, frame.frameIndex()),
              probe.width(),
              probe.height()));
    }
    uploadAll(files, items);
    FrameManifest manifest =
        new FrameManifest(
            videoId,
            context.jobId().toString(),
            new FrameManifest.Source(probe.width(), probe.height(), probe.fps()),
            items);
    String manifestKey = "videos/" + videoId + "/jobs/" + context.jobId() + "/frames.json";
    uploadManifest(context.workDir().resolve("frames.json"), manifestKey, manifest);
    store.recordFramesManifest(context.jobId(), manifestKey);
    context.framesExtracted(manifest);

    log.info(
        "프레임 추출 jobId={} frames={} bytes={} withStep={} extractMs={} uploadMs={}",
        context.jobId(),
        items.size(),
        bytes,
        items.stream().filter(i -> i.stepId() != null).count(),
        extractedMs,
        millisSince(started));
  }

  static String frameKey(String videoId, long frameIndex) {
    return "videos/" + videoId + "/frames/" + String.format("%06d", frameIndex) + ".jpg";
  }

  /** 동시에 {@code uploadConcurrency}장씩 올리고, 올린 파일은 지운다. 하나라도 실패하면 저장소 오류로 끝낸다. */
  private void uploadAll(List<Path> files, List<FrameManifest.Item> items) {
    ExecutorService pool =
        Executors.newFixedThreadPool(Math.max(1, properties.uploadConcurrency()));
    try {
      List<Future<?>> futures = new ArrayList<>(files.size());
      for (int i = 0; i < files.size(); i++) {
        Path file = files.get(i);
        String key = items.get(i).key();
        futures.add(
            pool.submit(
                () -> {
                  storage.upload(file, key, "image/jpeg");
                  Files.deleteIfExists(file);
                  return null;
                }));
      }
      for (Future<?> future : futures) {
        future.get();
      }
    } catch (ExecutionException e) {
      Throwable cause = e.getCause();
      throw new AnalysisStepException(
          AnalysisFailureCode.STORAGE_UNAVAILABLE, "프레임을 올리지 못했습니다: " + cause.getMessage(), cause);
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new AnalysisStepException(
          AnalysisFailureCode.STORAGE_UNAVAILABLE, "프레임을 올리다 중단됐습니다.", e);
    } finally {
      pool.shutdownNow();
    }
  }

  private void uploadManifest(Path file, String key, FrameManifest manifest) {
    try {
      Files.writeString(file, objectMapper.writeValueAsString(manifest), StandardCharsets.UTF_8);
      storage.upload(file, key, "application/json");
    } catch (IOException | StorageException e) {
      throw new AnalysisStepException(
          AnalysisFailureCode.STORAGE_UNAVAILABLE, "프레임 목록을 올리지 못했습니다: " + key, e);
    }
  }

  private static long totalBytes(List<Path> files) {
    long sum = 0;
    for (Path file : files) {
      try {
        sum += Files.size(file);
      } catch (IOException e) {
        // 크기는 로그용이라 넘어간다
      }
    }
    return sum;
  }

  private static long millisSince(long nanoStart) {
    return (System.nanoTime() - nanoStart) / 1_000_000;
  }
}
