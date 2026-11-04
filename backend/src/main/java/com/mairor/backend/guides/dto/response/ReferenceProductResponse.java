package com.mairor.backend.guides.dto.response;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;

/**
 * 단계에서 쓴 제품(API 명세 v2 ReferenceProduct). 1차는 영상에 나온 이름만 있고 제품 DB 와 맞추지 않아(ANALYSIS-003) 늘 {@code
 * UNMATCHED} 다. 화면 라벨: UNMATCHED = '이름만 확인'.
 */
public record ReferenceProductResponse(
    @Schema(description = "카탈로그 제품 ID. 1차는 null") String productId,
    @Schema(description = "카탈로그 호수 ID. 1차는 null") String shadeId,
    @Schema(description = "브랜드와 제품 이름", example = "롬앤 베러 댄 팔레트") String name,
    @Schema(description = "호수·색 이름. 없으면 null", example = "06 포멜로 로즈") String shadeName,
    @Schema(description = "MATCHED·CANDIDATE·UNMATCHED", example = "UNMATCHED") String matchStatus,
    @Schema(description = "CONFIRMED·ESTIMATED·UNKNOWN", example = "UNKNOWN") String verification,
    @Schema(description = "근거 출처. 1차는 빈 목록") List<String> sources,
    @Schema(description = "영상에서 확인됐는지. 영상에서 뽑은 제품이라 true", example = "true")
        Boolean videoConfirmed) {}
