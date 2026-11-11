package com.mairor.backend.history.dto;

import com.mairor.backend.photos.dto.PhotoResponse;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * 리포트 상세(API 명세 v2 ReportRecord)의 Swagger 모양. 응답은 완료할 때 저장한 {@code record_snapshot} JSON 을 그대로 보내므로
 * 이 레코드로 만들지 않는다(S15P31A306-404).
 */
@Schema(name = "ReportRecord", description = "완료할 때 고정한 리포트 전체. 이후 가이드 · 파우치가 바뀌어도 그대로다")
public record ReportRecordSchema(
    @Schema(description = "리포트 ID", example = "00000000-0000-4000-8000-000000000601") UUID recordId,
    @Schema(description = "실행 ID", example = "00000000-0000-4000-8000-000000000501")
        UUID executionId,
    @Schema(description = "내부 영상 ID", example = "00000000-0000-4000-8000-000000000101")
        UUID videoId,
    @Schema(description = "완료할 때의 영상 제목", example = "데일리 메이크업 튜토리얼") String videoTitle,
    @Schema(description = "완료할 때의 채널 이름", example = "메이크업채널") String channelTitle,
    @Schema(description = "가이드 ID", example = "00000000-0000-4000-8000-000000000201") UUID guideId,
    @Schema(description = "따라 한 가이드 판 번호", example = "1") int guideVersion,
    @Schema(description = "완료 시각(UTC)", example = "2026-11-11T09:00:00Z") Instant completedAt,
    @Schema(description = "완성 사진(마지막 단계 사진). 없으면 null") PhotoResponse completedPhoto,
    @Schema(description = "단계 수", example = "12") int stepCount,
    @Schema(description = "대체 제품으로 따라 한 단계 수", example = "3") int substituteCount,
    @Schema(
            description =
                "단계(ReportStep): GuideStep 모든 칸 + matchingResult(SAME · SUBSTITUTE · NONE) · selectedProduct ·"
                    + " selectedColorId · selectedColor · skipped · photo(null 이면 미촬영)")
        List<Map<String, Object>> steps) {}
