package com.mairor.backend.analysis.worker;

import com.mairor.backend.analysis.entity.AnalysisFailureCode;
import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.entity.ProgressStage;
import com.mairor.backend.analysis.repository.AnalysisJobRepository;
import com.mairor.backend.guides.entity.Guide;
import com.mairor.backend.guides.repository.GuideRepository;
import com.mairor.backend.videos.entity.Video;
import com.mairor.backend.videos.repository.VideoRepository;
import java.nio.file.Path;
import java.time.Clock;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/** worker 의 짧은 트랜잭션들. 실행기는 단계 사이사이에 이것만 부르고, 내려받기·외부 호출 같은 긴 일은 트랜잭션 밖에서 한다(행 잠금을 오래 쥐지 않게). */
@Component
public class AnalysisJobStore {

  private final AnalysisJobRepository jobs;
  private final VideoRepository videos;
  private final GuideRepository guides;
  private final Clock clock;

  AnalysisJobStore(
      AnalysisJobRepository jobs, VideoRepository videos, GuideRepository guides, Clock clock) {
    this.jobs = jobs;
    this.videos = videos;
    this.guides = guides;
    this.clock = clock;
  }

  /**
   * 단계 추출 결과(가이드 입력 JSON)를 작업의 가이드에 저장한다. 작업당 가이드는 하나라 이미 있으면(멈춘 작업을 다시 돌림) 입력만 바꾸고, 없으면 그 영상의 다음
   * 판으로 만든다. 검수 상태는 설명·영역이 오기 전이라 {@code NOT_READY}다.
   *
   * @return 가이드 ID
   */
  @Transactional
  public UUID saveGuideInput(UUID jobId, String guideInputJson) {
    AnalysisJob job = load(jobId);
    Optional<Guide> existing = guides.findByAnalysisJobId(jobId);
    if (existing.isPresent()) {
      existing.get().replaceGuideInput(guideInputJson);
      return existing.get().getId();
    }
    int version = guides.findMaxVersionByVideoId(job.getVideo().getId()) + 1;
    return guides.save(new Guide(job, version, guideInputJson)).getId();
  }

  /** 가장 오래 기다린 PENDING 작업을 집어 RUNNING 으로 바꾼다. 없으면 빈 값. */
  @Transactional
  public Optional<AnalysisContext> claimNext(Path workRoot) {
    return jobs.lockNextPending()
        .map(
            job -> {
              job.start(clock.instant());
              Video video = job.getVideo();
              return new AnalysisContext(
                  job.getId(),
                  video.getId(),
                  video.getYoutubeVideoId(),
                  video.getSourceObjectKey(),
                  workRoot.resolve(job.getId().toString()));
            });
  }

  /** 작업의 가이드에 프레임 목록 키를 적는다. 단계 추출이 가이드를 먼저 만든다. */
  @Transactional
  public void recordFramesManifest(UUID jobId, String key) {
    guides.findByAnalysisJobId(jobId).orElseThrow().useFramesManifest(key);
  }

  /** AI 서버에 맡긴 작업 ID 를 적는다. 작업은 콜백이 끝낼 때까지 RUNNING 이다. */
  @Transactional
  public void awaitAi(UUID jobId, String aiJobId) {
    load(jobId).awaitAi(aiJobId);
  }

  @Transactional
  public void advance(UUID jobId, ProgressStage stage) {
    load(jobId).advanceTo(stage);
  }

  @Transactional
  public void complete(UUID jobId) {
    load(jobId).complete(clock.instant());
  }

  @Transactional
  public void fail(UUID jobId, AnalysisFailureCode code, String message) {
    load(jobId).fail(code, message, clock.instant());
  }

  @Transactional
  public void recordSourceProbe(UUID videoId, VideoProbe probe) {
    Video video = videos.findById(videoId).orElseThrow();
    video.recordSourceProbe(probe.width(), probe.height(), probe.fps(), probe.durationSeconds());
  }

  /**
   * worker 가 처리 중에 죽어 RUNNING 으로 남은 작업을 PENDING 으로 되돌린다. worker 가 하나라는 전제다(둘 이상이면 다른 worker 가 처리 중인
   * 작업까지 되돌린다).
   *
   * @return 되돌린 작업 수
   */
  @Transactional
  public int requeueRunning() {
    List<AnalysisJob> running = jobs.findByStatusAndAiJobIdIsNull(AnalysisStatus.RUNNING);
    running.forEach(AnalysisJob::requeueAfterCrash);
    return running.size();
  }

  private AnalysisJob load(UUID jobId) {
    return jobs.findById(jobId).orElseThrow();
  }
}
