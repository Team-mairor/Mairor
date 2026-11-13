package com.mairor.backend.products.dto.response;

import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;

/** 화장품 카테고리 하나와 그 안의 종류. */
public record ProductCategoryResponse(
    @Schema(description = "카테고리 코드. 파우치 등록·제품 검색에 이 값을 보낸다", example = "BASE") String code,
    @Schema(description = "화면에 보여 줄 이름", example = "베이스") String label,
    @Schema(description = "보유 화장품 매칭(동일·대체) 대상인지", example = "true") boolean matchable,
    @Schema(description = "등록할 때 호수·컬러를 고르는 카테고리인지", example = "true") boolean shadeSelectable,
    @ArraySchema(arraySchema = @Schema(description = "세부 종류. 표시 순서대로 오며, 종류가 없으면 빈 목록"))
        List<ProductTypeResponse> types,
    @Schema(description = "카테고리 호환 부위 코드. 현재 시드는 빈 목록이며, 추천 매칭은 종류 코드 기준 정책으로 판정", example = "[]")
        List<String> compatibleParts) {}
