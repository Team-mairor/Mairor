package com.mairor.backend.videos.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;

/** 검색 한 페이지(API 명세 v2 VideoSearchPage). YouTube 검색이라 page 대신 pageToken 을 쓴다. */
public record VideoSearchPage(
    @Schema(description = "관련도순 결과. 분석할 수 없는 영상을 걸러 size 보다 적을 수 있다") List<VideoSearchItem> items,
    @Schema(description = "다음 페이지 토큰. 마지막 페이지는 null", example = "CBQQAA") String nextPageToken,
    @Schema(description = "요청한 size", example = "20") int size) {}
