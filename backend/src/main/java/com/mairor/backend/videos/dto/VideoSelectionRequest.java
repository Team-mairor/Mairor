package com.mairor.backend.videos.dto;

import io.swagger.v3.oas.annotations.media.Schema;

/** 영상 선택 요청(API-VIDEO-001). */
public record VideoSelectionRequest(
    @Schema(description = "YouTube 영상 ID(11자)", example = "VxAXD6PP76I") String youtubeVideoId) {}
