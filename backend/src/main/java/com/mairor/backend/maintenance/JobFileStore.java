package com.mairor.backend.maintenance;

import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.repository.AnalysisJobRepository;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/** 저장소 정리가 쓰는 작업 읽기 · 바꾸기. 저장소 호출(느림)을 DB 트랜잭션 밖에 두려고 따로 뺐다. */
@Component
public class JobFileStore {

  private static final List<AnalysisStatus> FINISHED =
      List.of(AnalysisStatus.COMPLETED, AnalysisStatus.FAILED);
  private static final List<AnalysisStatus> ACTIVE =
      List.of(AnalysisStatus.PENDING, AnalysisStatus.RUNNING);

  /** 끝난 작업. */
  public record FinishedJob(UUID jobId, UUID videoId, String youtubeVideoId) {}

  private final AnalysisJobRepository jobs;

  JobFileStore(AnalysisJobRepository jobs) {
    this.jobs = jobs;
  }

  @Transactional(readOnly = true)
  public List<FinishedJob> finishedBetween(Instant from, Instant to) {
    return jobs.findFinishedBetween(FINISHED, from, to).stream()
        .map(
            j -> new FinishedJob(j.getId(), j.getVideo().getId(), j.getVideo().getYoutubeVideoId()))
        .toList();
  }

  /**
   * 파일을 지우기 직전에 작업을 잠그고 다시 본다. 아직 끝난 상태이고 {@code keepFrom} 전에 끝났으면 true 다. 실패 작업은 노트북 결과 표시도 지워,
   * 나중에 다시 시도하면 처음부터 돈다. 목록을 읽은 뒤 회원이 다시 시도해(같은 잠금) 대기열 · 진행 중이면 false 이고, 그 작업의 파일은 지우지 않는다.
   */
  @Transactional
  public boolean releaseForCleanup(UUID jobId, Instant keepFrom) {
    return jobs.lockById(jobId)
        .filter(j -> FINISHED.contains(j.getStatus()))
        .filter(j -> j.getFinishedAt() != null && j.getFinishedAt().isBefore(keepFrom))
        .map(
            j -> {
              j.forgetProcessorOutput();
              return true;
            })
        .orElse(false);
  }

  /** 진행 중 작업이 없고, {@code since} 이후에 끝난 작업도 없는 영상인가(옛 공유 프레임을 지워도 되는가). */
  @Transactional(readOnly = true)
  public boolean quietSince(UUID videoId, Instant since) {
    return !jobs.existsByVideoIdAndStatusIn(videoId, ACTIVE)
        && !jobs.existsByVideoIdAndFinishedAtGreaterThanEqual(videoId, since);
  }
}
