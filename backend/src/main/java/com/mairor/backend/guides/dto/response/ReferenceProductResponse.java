package com.mairor.backend.guides.dto.response;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;

/**
 * 단계에서 쓴 제품(API 명세 v2 ReferenceProduct). 카탈로그 대조 뒤 확인된 연결 수준의 ID 만 포함한다. 화면 라벨: UNMATCHED = '이름만
 * 확인'.
 */
public record ReferenceProductResponse(
    @Schema(description = "유일하게 확인된 카탈로그 제품 ID. 연결되지 않으면 null") String productId,
    @Schema(description = "유일하게 확인된 카탈로그 호수 ID. 제품만 연결됐거나 미연결이면 null") String shadeId,
    @Schema(description = "브랜드와 제품 이름", example = "롬앤 베러 댄 팔레트") String name,
    @Schema(description = "호수·색 이름. 없으면 null", example = "06 포멜로 로즈") String shadeName,
    @Schema(description = "MATCHED·CANDIDATE·UNMATCHED", example = "UNMATCHED") String matchStatus,
    @Schema(description = "CONFIRMED·ESTIMATED·UNKNOWN", example = "UNKNOWN") String verification,
    @Schema(description = "근거 출처. 현재는 빈 목록") List<String> sources,
    @Schema(description = "영상에서 확인됐는지. 영상에서 뽑은 제품이라 true", example = "true")
        Boolean videoConfirmed) {}
