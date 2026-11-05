package com.mairor.backend.pouch.dto;

import io.swagger.v3.oas.annotations.media.Schema;

/** 내 파우치 목록의 선택 필터. page·size는 공통 {@code PageQuery}로 받는다. */
public record PouchListQuery(
    @Schema(description = "카테고리 코드. 생략하면 전체 카테고리", example = "LIP") String category,
    @Schema(description = "종류 코드. 생략하면 전체 종류", example = "LIP_TINT") String type) {}
