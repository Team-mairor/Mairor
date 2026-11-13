package com.mairor.backend.maintenance;

import com.mairor.backend.analysis.log.AnalysisLogContext;
import com.mairor.backend.common.storage.ObjectStorage;
import com.mairor.backend.maintenance.JobFileStore.FinishedJob;
import java.time.Clock;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * 끝난 작업의 저장소 파일 정리(S15P31A306-407). 보관 기간(기본 7일)이 지난 작업의 {@code videos/<yt>/jobs/<jobId>/}(노트북 프레임
 * · {@code frames.json} · {@code guide_job_request.json})를 지우고, 진행 중 작업이 없고 마지막 작업도 그만큼 지난 영상의 옛 BE
 * worker 모드 공유 프레임 {@code videos/<yt>/frames/}도 지운다. 원본 영상({@code source.mp4})과 가이드(DB)는 남긴다.
 *
 * <p>S3 수명 규칙은 경로 가운데({@code jobs})에 와일드카드를 걸 수 없어 여기서 지운다. 프레임은 AI 가 가이드를 만드는 동안과 "가이드 단계부터 다시
 * 시도"에만 쓴다. 재시도 가능 실패 작업은 지우기 전에 그 표시를 지워, 나중에 다시 시도하면 처음부터 돈다.
 */
@Service
public class JobFileCleanup {

  /** 한 번 정리한 결과. */
  public record Result(int jobs, int objects, int sharedFrameVideos, int failed) {}

  private static final Logger log = LoggerFactory.getLogger(JobFileCleanup.class);

  private final JobFileStore store;
  private final ObjectStorage storage;
  private final MaintenanceProperties properties;
  private final Clock clock;

  JobFileCleanup(
      JobFileStore store, ObjectStorage storage, MaintenanceProperties properties, Clock clock) {
    this.store = store;
    this.storage = storage;
    this.properties = properties;
    this.clock = clock;
  }

  public Result run() {
    Instant now = clock.instant();
    Instant keepFrom = now.minus(properties.jobFilesKeep());
    List<FinishedJob> finished =
        store.finishedBetween(now.minus(properties.jobFilesLookback()), keepFrom);
    int jobs = 0;
    int objects = 0;
    int failed = 0;
    Map<UUID, String> videos = new LinkedHashMap<>();
    for (FinishedJob job : finished) {
      videos.put(job.videoId(), job.youtubeVideoId());
      try (var ignored = AnalysisLogContext.of(job.jobId(), job.youtubeVideoId(), null)) {
        if (!store.releaseForCleanup(job.jobId(), keepFrom)) {
          // 목록을 읽은 뒤 다시 시도했다. 같은 작업 폴더에 새 파일을 쓸 수 있다
          continue;
        }
        int deleted = storage.deletePrefix(jobPrefix(job));
        if (deleted > 0) {
          jobs++;
          objects += deleted;
        }
      } catch (RuntimeException e) {
        failed++;
        log.warn("작업 파일을 지우지 못함 jobId={}", job.jobId(), e);
      }
    }
    int sharedFrameVideos = 0;
    for (Map.Entry<UUID, String> video : videos.entrySet()) {
      try {
        // 확인 뒤 새 작업이 생겨도 이 폴더에 프레임을 쓰기까지는 영상 받기 · 단계 추출(Gemini)로 수십 초가 걸려, 바로 지우는 것과 겹치지 않는다
        if (store.quietSince(video.getKey(), keepFrom)) {
          int deleted = storage.deletePrefix("videos/" + video.getValue() + "/frames/");
          if (deleted > 0) {
            sharedFrameVideos++;
            objects += deleted;
          }
        }
      } catch (RuntimeException e) {
        failed++;
        log.warn("영상 공유 프레임을 지우지 못함 youtubeVideoId={}", video.getValue(), e);
      }
    }
    Result result = new Result(jobs, objects, sharedFrameVideos, failed);
    log.atInfo()
        .setMessage("저장소 정리 jobs={} objects={} sharedFrameVideos={} failed={}")
        .addArgument(jobs)
        .addArgument(objects)
        .addArgument(sharedFrameVideos)
        .addArgument(failed)
        .addKeyValue("cleaned_jobs", jobs)
        .addKeyValue("deleted_objects", objects)
        .log();
    return result;
  }

  static String jobPrefix(FinishedJob job) {
    return "videos/" + job.youtubeVideoId() + "/jobs/" + job.jobId() + "/";
  }
}
