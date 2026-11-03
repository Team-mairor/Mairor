package com.mairor.backend.analysis.dto.response;

import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.entity.ProgressStage;
import com.mairor.backend.analysis.service.AnalysisJobView;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.UUID;

/** 운영자가 보는 분석 작업 상태. 실패 원인(failureMessage)과 영상 파일 원본 정보까지 보여 준다. */
public record InternalAnalysisJobResponse(
    @Schema(description = "분석 작업 ID") UUID jobId,
    @Schema(description = "내부 영상 ID") UUID videoId,
    @Schema(description = "유튜브 영상 ID", example = "VxAXD6PP76I") String youtubeVideoId,
    @Schema(description = "작업 상태", example = "COMPLETED") AnalysisStatus status,
    @Schema(description = "진행 단계. FAILED 면 멈춘 단계", example = "DONE") ProgressStage progressStage,
    @Schema(description = "다시 시도하면 될 수 있는 실패인지") boolean retryable,
    @Schema(description = "실패 원인 코드. 실패가 아니면 null", example = "SOURCE_NOT_FOUND")
        String failureCode,
    @Schema(description = "실패 원인 설명. 실패가 아니면 null") String failureMessage,
    @Schema(description = "몇 번째 시도인지", example = "1") int attempt,
    @Schema(description = "접수 시각") Instant createdAt,
    @Schema(description = "worker 가 집은 시각. 대기 중이면 null") Instant startedAt,
    @Schema(description = "끝난 시각. 진행 중이면 null") Instant finishedAt,
    @Schema(description = "분석에 쓴 영상 파일. 원본 정보는 영상 불러오기 단계 뒤에 채워진다") Source source) {

  public record Source(
      @Schema(description = "저장소 키", example = "videos/VxAXD6PP76I/source.mp4") String objectKey,
      @Schema(description = "가로(px)", example = "1920") Integer width,
      @Schema(description = "세로(px)", example = "1080") Integer height,
      @Schema(description = "평균 fps", example = "60.0") Double fps,
      @Schema(description = "길이(초)", example = "1858.2") Double durationSeconds) {}

  public static InternalAnalysisJobResponse from(AnalysisJobView view) {
    AnalysisJobView.Source s = view.source();
    return new InternalAnalysisJobResponse(
        view.jobId(),
        view.videoId(),
        view.youtubeVideoId(),
        view.status(),
        view.progressStage(),
        view.retryable(),
        view.failureCode(),
        view.failureMessage(),
        view.attempt(),
        view.createdAt(),
        view.startedAt(),
        view.finishedAt(),
        new Source(s.objectKey(), s.width(), s.height(), s.fps(), s.durationSeconds()));
  }
}
