package com.mairor.backend.analysis.dto.request;

import io.swagger.v3.oas.annotations.media.Schema;

/**
 * AI 서버 진행 알림 본문({@code docs/references/ai-api.md} "진행 알림", AI {@code GuideJobProgress}). API
 * 문서용이다. 받을 때는 받을 수 없는 알림도 204 로 답하려고 문자열로 받아 직접 검사한다({@code AiProgressService}).
 */
public record AiGuideJobProgressRequest(
    @Schema(
            description = "AI 작업 ID(가이드 생성 요청의 202 응답)",
            example = "8728c83b0d124c74a23863a50d4d7c0c")
        String jobId,
    @Schema(description = "설명이 끝난 단계(실패한 단계 포함)") Count explanation,
    @Schema(description = "받기를 끝낸 사진(못 받은 사진 포함). 프레임 없이 맡긴 작업이면 null", nullable = true)
        Count frames,
    @Schema(description = "얼굴 점을 찾아 본 사진. 프레임 없이 맡긴 작업이면 null", nullable = true) Count landmarks,
    @Schema(description = "영역이 끝난 단계. 프레임 없이 맡긴 작업이면 null", nullable = true) Count area) {

  /** 센 수. {@code 0 <= done <= total}. */
  public record Count(
      @Schema(description = "끝난 수", example = "840") long done,
      @Schema(description = "전체 수", example = "2000") long total) {}
}
