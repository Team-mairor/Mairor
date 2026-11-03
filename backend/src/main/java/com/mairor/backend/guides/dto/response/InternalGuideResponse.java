package com.mairor.backend.guides.dto.response;

import com.fasterxml.jackson.annotation.JsonRawValue;
import com.mairor.backend.guides.entity.ReviewStatus;
import com.mairor.backend.guides.service.GuideView;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.UUID;

/** 운영자가 검수할 때 보는 가이드. 입력·설명·영역은 저장된 JSON 그대로 싣는다. */
public record InternalGuideResponse(
    @Schema(description = "가이드 ID") UUID guideId,
    @Schema(description = "이 가이드를 만든 분석 작업 ID") UUID analysisJobId,
    @Schema(description = "유튜브 영상 ID", example = "VxAXD6PP76I") String youtubeVideoId,
    @Schema(description = "같은 영상 안에서의 판 번호(1부터)", example = "1") int version,
    @Schema(description = "검수 상태. 설명·영역이 오기 전 NOT_READY, 온 뒤 PENDING", example = "PENDING")
        ReviewStatus reviewStatus,
    @Schema(description = "얼굴 메시 판(영역이 있을 때)", example = "v1") String meshVersion,
    @Schema(description = "프레임 목록(frames.json) 저장소 키") String framesManifestKey,
    @Schema(description = "검수한 시각. 검수 전이면 null") Instant reviewedAt,
    @Schema(description = "만든 시각") Instant createdAt,
    @Schema(description = "가이드 입력(AI 에 보낸 단계 목록)", type = "object") @JsonRawValue String guideInput,
    @Schema(description = "쉬운 설명(AI 콜백 guide). 오기 전이면 null", type = "object") @JsonRawValue
        String explanation,
    @Schema(description = "가이드 영역(AI 콜백 area). 없으면 null", type = "object") @JsonRawValue
        String area) {

  public static InternalGuideResponse from(GuideView view) {
    return new InternalGuideResponse(
        view.guideId(),
        view.analysisJobId(),
        view.youtubeVideoId(),
        view.version(),
        view.reviewStatus(),
        view.meshVersion(),
        view.framesManifestKey(),
        view.reviewedAt(),
        view.createdAt(),
        view.guideInput(),
        view.explanation(),
        view.area());
  }
}
