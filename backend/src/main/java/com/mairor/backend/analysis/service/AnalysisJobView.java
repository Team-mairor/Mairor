package com.mairor.backend.analysis.service;

import com.mairor.backend.analysis.entity.AnalysisJob;
import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.entity.ProgressStage;
import com.mairor.backend.videos.entity.Video;
import java.time.Instant;
import java.util.UUID;

/** 운영자가 보는 작업 상태 한 건. 영상 파일 원본 정보(ffprobe 값)는 첫 단계가 끝나야 채워진다. */
public record AnalysisJobView(
    UUID jobId,
    UUID videoId,
    String youtubeVideoId,
    AnalysisStatus status,
    ProgressStage progressStage,
    boolean retryable,
    String failureCode,
    String failureMessage,
    int attempt,
    Instant createdAt,
    Instant startedAt,
    Instant finishedAt,
    Source source,
    String aiJobId,
    UUID guideId) {

  /** 분석에 쓴 영상 파일. ffprobe 전에는 키만 있다. */
  public record Source(
      String objectKey, Integer width, Integer height, Double fps, Double durationSeconds) {}

  static AnalysisJobView of(AnalysisJob job, UUID guideId) {
    Video video = job.getVideo();
    return new AnalysisJobView(
        job.getId(),
        video.getId(),
        video.getYoutubeVideoId(),
        job.getStatus(),
        job.getProgressStage(),
        job.isRetryable(),
        job.getFailureCode(),
        job.getFailureMessage(),
        job.getAttempt(),
        job.getCreatedAt(),
        job.getStartedAt(),
        job.getFinishedAt(),
        new Source(
            video.getSourceObjectKey(),
            video.getSourceWidth(),
            video.getSourceHeight(),
            video.getSourceFps(),
            video.getSourceDurationSeconds()),
        job.getAiJobId(),
        guideId);
  }
}
