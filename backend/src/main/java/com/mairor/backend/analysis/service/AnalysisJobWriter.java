package com.mairor.backend.analysis.service;

import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.repository.AnalysisJobRepository;
import com.mairor.backend.videos.entity.Video;
import com.mairor.backend.videos.repository.VideoRepository;
import java.time.Clock;
import java.util.EnumSet;
import java.util.Optional;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * 작업 접수의 트랜잭션 한 번. 동시 요청이 유일 제약({@code uk_videos_youtube_video_id}·{@code
 * uk_analysis_jobs_video_active})에 걸리면 이 트랜잭션은 롤백되고, {@link AnalysisJobService}가 새 트랜잭션으로 다시 시도한다.
 */
@Component
class AnalysisJobWriter {

  static final EnumSet<AnalysisStatus> ACTIVE =
      EnumSet.of(AnalysisStatus.PENDING, AnalysisStatus.RUNNING);

  private final VideoRepository videos;
  private final AnalysisJobRepository jobs;
  private final Clock clock;

  AnalysisJobWriter(VideoRepository videos, AnalysisJobRepository jobs, Clock clock) {
    this.videos = videos;
    this.jobs = jobs;
    this.clock = clock;
  }

  /**
   * 영상이 없으면 만들고, 진행 중 작업이 있으면 그 작업을 돌려주고(JOINED_JOB), 없으면 영상 파일 키를 정해 새 작업을 만든다(NEW_JOB). 이미 있는 영상의
   * 메타는 바꾸지 않는다.
   */
  @Transactional
  AnalysisJobReceipt register(AnalysisJobRequest request) {
    Video video =
        videos
            .findByYoutubeVideoId(request.youtubeVideoId())
            .orElseGet(() -> videos.saveAndFlush(newVideo(request)));

    Optional<AnalysisJob> active = jobs.findFirstByVideoIdAndStatusIn(video.getId(), ACTIVE);
    if (active.isPresent()) {
      return AnalysisJobReceipt.of(active.get(), ReceiptType.JOINED_JOB);
    }
    video.useSourceObject(request.sourceObjectKey());
    AnalysisJob job = jobs.saveAndFlush(new AnalysisJob(video, null));
    return AnalysisJobReceipt.of(job, ReceiptType.NEW_JOB);
  }

  private Video newVideo(AnalysisJobRequest request) {
    return new Video(
        request.youtubeVideoId(),
        request.title(),
        request.channelTitle(),
        request.durationSeconds(),
        "https://i.ytimg.com/vi/" + request.youtubeVideoId() + "/hqdefault.jpg",
        null,
        "[]",
        clock.instant());
  }
}
