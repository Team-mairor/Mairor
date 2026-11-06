package com.mairor.backend.videos.dto;

import io.swagger.v3.oas.annotations.media.Schema;

/** 설명란 챕터(API 명세 v2 VideoChapter). */
public record VideoChapter(
    @Schema(description = "챕터 시작 시각(초)", example = "95") int startSeconds,
    @Schema(description = "챕터 이름", example = "아이섀도") String label) {}
