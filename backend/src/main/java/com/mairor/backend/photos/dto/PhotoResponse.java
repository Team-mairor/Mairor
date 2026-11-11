package com.mairor.backend.photos.dto;

import com.mairor.backend.photos.entity.PhotoKind;
import com.mairor.backend.photos.entity.StoredPhoto;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.UUID;

public record PhotoResponse(
    @Schema(description = "사진 ID", example = "00000000-0000-4000-8000-000000000301") UUID photoId,
    @Schema(description = "사진 용도", example = "FACE_REGISTRATION") PhotoKind kind,
    @Schema(description = "단계 사진의 단계 ID", example = "step-1", nullable = true) String stepId,
    @Schema(description = "실제 사진 MIME", example = "image/png") String contentType,
    @Schema(description = "파일 크기 바이트", example = "102400") long byteSize,
    @Schema(description = "이미지 가로 픽셀", example = "640") int width,
    @Schema(description = "이미지 세로 픽셀", example = "480") int height,
    @Schema(
            description = "인증이 필요한 사진 조회 상대 경로",
            example = "/api/v1/users/me/photos/00000000-0000-4000-8000-000000000301")
        String url,
    @Schema(description = "사진 생성 시각", example = "2026-11-09T00:00:00Z") Instant createdAt) {
  public static PhotoResponse from(StoredPhoto photo) {
    return new PhotoResponse(
        photo.getId(),
        photo.getKind(),
        photo.getStepId(),
        photo.getContentType(),
        photo.getByteSize(),
        photo.getWidth(),
        photo.getHeight(),
        "/api/v1/users/me/photos/" + photo.getId(),
        photo.getCreatedAt());
  }
}
