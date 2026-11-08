package com.mairor.backend.guides.dto.response;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import java.util.UUID;

/**
 * 검수 승인된 가이드(API-ANALYSIS-001, API 명세 v2 Guide 를 가이드 영역 형식으로 고친 것). 좌표는 {@code coordinateSystem} 대신
 * 얼굴 메시 판({@code meshVersion})이다.
 */
public record GuideResponse(
    @Schema(description = "가이드 ID") UUID guideId,
    @Schema(description = "같은 영상 안에서의 판 번호(1부터)", example = "1") int guideVersion,
    @Schema(description = "내부 영상 ID") UUID videoId,
    @Schema(description = "유튜브 영상 ID", example = "VxAXD6PP76I") String youtubeVideoId,
    @Schema(description = "영상 제목", example = "완성도 up! 요즘 진짜 예뻐진 메이크업") String title,
    @Schema(description = "채널 이름", example = "GO지승") String channelTitle,
    @Schema(description = "썸네일 주소. 없으면 null") String thumbnailUrl,
    @Schema(description = "가이드 영역의 얼굴 메시 판. 영역이 없으면 null", example = "v1") String meshVersion,
    @Schema(description = "레퍼런스 대표 이미지. 1차는 항상 null") String referenceImageUrl,
    @Schema(description = "따라 하는 단계(GUIDE) 수. 제외 단계는 세지 않는다", example = "26") int stepCount,
    @Schema(description = "미리보기 가능한 단계 수", example = "12") int previewableStepCount,
    @Schema(description = "단계 목록(order 순). GUIDE·EXCLUDED 가 섞여 있다")
        List<GuideStepResponse> steps) {}
