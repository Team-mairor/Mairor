package com.mairor.backend.analysis.dto.response;

import com.mairor.backend.analysis.service.ProcessorJobService;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.UUID;

/** 노트북에 내준 작업. */
public record ProcessorClaimResponse(
    @Schema(description = "분석 작업 ID. 완료 · 실패 · 진행 알림 경로에 쓴다") UUID jobId,
    @Schema(description = "YouTube 영상 ID", example = "VxAXD6PP76I") String youtubeVideoId,
    @Schema(description = "받을 영상 주소", example = "https://www.youtube.com/watch?v=VxAXD6PP76I")
        String youtubeUrl,
    @Schema(
            description = "이 작업의 파일(프레임 · AI 요청 JSON)을 올릴 저장소 경로. 버킷은 운영 미디어 버킷",
            example = "videos/VxAXD6PP76I/jobs/2c1f4b7e-9a3d-4c5e-8f60-1a2b3c4d5e6f")
        String s3Prefix,
    @Schema(description = "임대 시간(초). 이 안에 완료 · 실패 · 진행 알림이 없으면 작업을 다시 내준다", example = "900")
        long leaseSeconds) {

  public static ProcessorClaimResponse from(ProcessorJobService.Claim claim) {
    return new ProcessorClaimResponse(
        claim.jobId(),
        claim.youtubeVideoId(),
        claim.youtubeUrl(),
        claim.s3Prefix(),
        claim.leaseSeconds());
  }
}
