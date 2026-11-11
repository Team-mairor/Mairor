package com.mairor.backend.camera.dto;

import com.mairor.backend.camera.entity.FaceRegistration;
import com.mairor.backend.camera.entity.FaceRegistrationStatus;
import com.mairor.backend.photos.dto.PhotoResponse;
import com.mairor.backend.photos.entity.StoredPhoto;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.UUID;

public record FaceRegistrationResponse(
    @Schema(description = "얼굴 등록 ID", example = "00000000-0000-4000-8000-000000000401")
        UUID faceRegistrationId,
    @Schema(description = "내부 영상 ID", example = "00000000-0000-4000-8000-000000000101")
        UUID videoId,
    @Schema(
            description = "연결 가이드 ID",
            example = "00000000-0000-4000-8000-000000000201",
            nullable = true)
        UUID guideId,
    @Schema(
            description = "연결 실행 ID",
            example = "00000000-0000-4000-8000-000000000501",
            nullable = true)
        UUID executionId,
    @Schema(description = "얼굴 등록 상태", example = "REGISTERED") FaceRegistrationStatus status,
    @Schema(description = "사진 메타데이터") PhotoResponse photo,
    @Schema(description = "클라이언트 촬영 조건") FaceChecksData checks,
    @Schema(description = "동의한 안내 버전", example = "v1") String noticeVersion,
    @Schema(description = "서버 기록 동의 시각", example = "2026-11-09T00:00:00Z") Instant agreedAt,
    @Schema(description = "등록 생성 시각", example = "2026-11-09T00:00:00Z") Instant createdAt) {
  public static FaceRegistrationResponse from(FaceRegistration registration, StoredPhoto photo) {
    return new FaceRegistrationResponse(
        registration.getId(),
        registration.getVideoId(),
        registration.getGuideId(),
        registration.getExecutionId(),
        registration.getStatus(),
        PhotoResponse.from(photo),
        FaceChecksData.from(registration.getChecks()),
        registration.getNoticeVersion(),
        registration.getAgreedAt(),
        registration.getCreatedAt());
  }
}
