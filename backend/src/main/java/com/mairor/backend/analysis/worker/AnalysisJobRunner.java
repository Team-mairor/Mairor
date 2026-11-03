package com.mairor.backend.analysis.worker;

import com.mairor.backend.analysis.entity.AnalysisFailureCode;
import com.mairor.backend.analysis.entity.ProgressStage;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Stream;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * 작업 하나를 처음 단계부터 끝까지 돌린다. 등록된 {@link AnalysisStepHandler}만 {@link #STAGE_ORDER} 순서대로 실행하고, 처리기가 없는
 * 단계는 건너뛴다. 모든 단계가 끝나면 COMPLETED, 처리기가 실패하면 그 단계에 멈춘 채 FAILED 다.
 *
 * <p>순서: 단계 추출(EXTRACTING_STEPS)이 단계 경계를 정해야 프레임(SEGMENTING)을 뽑을 수 있어서, API 명세의 진행 단계 나열 순서와 달리 단계
 * 추출을 먼저 한다. 진행 표시는 명세 값을 그대로 쓴다.
 */
@Component
public class AnalysisJobRunner {

  /** 처리기를 실행하는 순서. QUEUED·DONE 은 상태 표시용이라 처리기가 없다. */
  public static final List<ProgressStage> STAGE_ORDER =
      List.of(
          ProgressStage.LOADING_VIDEO,
          ProgressStage.EXTRACTING_STEPS,
          ProgressStage.SEGMENTING,
          ProgressStage.RECOGNIZING_PRODUCTS,
          ProgressStage.BUILDING_GUIDE);

  private static final Logger log = LoggerFactory.getLogger(AnalysisJobRunner.class);

  private final AnalysisJobStore store;
  private final WorkerProperties properties;
  private final Map<ProgressStage, AnalysisStepHandler> handlers;

  public AnalysisJobRunner(
      AnalysisJobStore store, WorkerProperties properties, List<AnalysisStepHandler> handlers) {
    this.store = store;
    this.properties = properties;
    this.handlers = new EnumMap<>(ProgressStage.class);
    for (AnalysisStepHandler handler : handlers) {
      AnalysisStepHandler previous = this.handlers.put(handler.stage(), handler);
      if (previous != null) {
        throw new IllegalStateException(handler.stage() + " 단계 처리기가 둘입니다.");
      }
    }
  }

  /**
   * 대기 작업 하나를 집어 끝까지 돌린다.
   *
   * @return 처리한 작업이 있었으면 true
   */
  public boolean runNext() {
    Optional<AnalysisContext> claimed = store.claimNext(properties.workDir());
    if (claimed.isEmpty()) {
      return false;
    }
    run(claimed.get());
    return true;
  }

  private void run(AnalysisContext context) {
    long started = System.nanoTime();
    log.info("분석 시작 jobId={} youtubeVideoId={}", context.jobId(), context.youtubeVideoId());
    ProgressStage current = ProgressStage.QUEUED;
    boolean finishesLater = false;
    try {
      Files.createDirectories(context.workDir());
      for (ProgressStage stage : STAGE_ORDER) {
        AnalysisStepHandler handler = handlers.get(stage);
        if (handler == null) {
          log.debug("처리기가 없어 건너뜀 jobId={} stage={}", context.jobId(), stage);
          continue;
        }
        current = stage;
        store.advance(context.jobId(), stage);
        long stageStarted = System.nanoTime();
        handler.run(context);
        finishesLater = handler.finishesLater();
        log.info(
            "분석 단계 완료 jobId={} stage={} elapsedMs={}",
            context.jobId(),
            stage,
            millisSince(stageStarted));
      }
      if (finishesLater) {
        log.info(
            "AI 결과 대기 jobId={} stage={} elapsedMs={}",
            context.jobId(),
            current,
            millisSince(started));
      } else {
        store.complete(context.jobId());
        log.info("분석 완료 jobId={} elapsedMs={}", context.jobId(), millisSince(started));
      }
    } catch (AnalysisStepException e) {
      log.warn(
          "분석 실패 jobId={} stage={} code={} message={}",
          context.jobId(),
          current,
          e.code(),
          e.getMessage(),
          e.getCause());
      store.fail(context.jobId(), e.code(), e.getMessage());
    } catch (IOException | RuntimeException e) {
      log.error("분석 중 예기치 않은 오류 jobId={} stage={}", context.jobId(), current, e);
      store.fail(context.jobId(), AnalysisFailureCode.INTERNAL_ERROR, null);
    } finally {
      deleteQuietly(context.workDir());
    }
  }

  private static long millisSince(long nanoStart) {
    return (System.nanoTime() - nanoStart) / 1_000_000;
  }

  private static void deleteQuietly(Path dir) {
    if (!Files.exists(dir)) {
      return;
    }
    try (Stream<Path> paths = Files.walk(dir)) {
      paths
          .sorted(Comparator.reverseOrder())
          .forEach(
              path -> {
                try {
                  Files.deleteIfExists(path);
                } catch (IOException e) {
                  log.warn("작업 폴더를 지우지 못했습니다: {}", path);
                }
              });
    } catch (IOException e) {
      log.warn("작업 폴더를 지우지 못했습니다: {}", dir);
    }
  }
}
