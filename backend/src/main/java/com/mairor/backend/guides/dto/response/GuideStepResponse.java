package com.mairor.backend.guides.dto.response;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import tools.jackson.databind.JsonNode;

/**
 * 가이드 단계(API 명세 v2 GuideStep 을 고친 것). {@code application} 대신 가이드 영역의 하위 단계({@code subSteps}, {@code
 * shared/guide-area} 그대로), {@code instruction} 대신 요약·동작·끝내는 때.
 */
public record GuideStepResponse(
    @Schema(description = "단계 ID", example = "s8") String stepId,
    @Schema(description = "순서(1부터)", example = "8") int order,
    @Schema(
            description = "GUIDE: 따라 하는 단계, EXCLUDED: 스킨케어처럼 가이드 대상이 아니라 진행률에서 빠지는 단계",
            example = "GUIDE")
        StepType type,
    @Schema(
            description =
                "화장 종류(foundation·eyeshadow·eyeliner·blush·lip·brow·mascara·contour·highlight·other)",
            example = "eyeshadow")
        String part,
    @Schema(description = "한국어 부위 이름", example = "윗눈두덩이") String partLabel,
    @Schema(description = "이 단계에서 하는 일 한 문장(영상 그대로)") String summary,
    @Schema(
            description = "순서대로 할 동작 [{text, tip: {kind: tip|caution, text}|null}]. 설명이 없으면 빈 목록",
            type = "array")
        JsonNode actions,
    @Schema(description = "다음 단계로 넘어가도 되는 때. 근거가 없으면 null") String doneWhen,
    @Schema(description = "쓰는 도구", example = "[\"섀도 브러시\"]") List<String> tools,
    @Schema(description = "영상에 나온 제품. 없으면 null") ReferenceProductResponse referenceProduct,
    @Schema(description = "목표 발색(ColorInfo). 1차는 항상 null", type = "object") JsonNode targetColor,
    @Schema(description = "영상 구간") VideoRange videoRange,
    @Schema(description = "미리보기 가능 여부. 색이 있는 단계(아이섀도·아이라인·블러셔·하이라이트·립)만 true") boolean previewable,
    @Schema(description = "제품 매칭 카테고리(BASE·EYE·BROW·CHEEK·LIP). 제외 단계는 null", example = "EYE")
        String matchCategory,
    @Schema(
            description =
                "가이드 영역의 하위 단계(shared/guide-area 의 subSteps 그대로, 상태 extracted·template·notApplicable·failed). 영역이 없으면 빈 목록",
            type = "array")
        JsonNode subSteps) {

  public enum StepType {
    GUIDE,
    EXCLUDED
  }

  public record VideoRange(
      @Schema(description = "시작(초)", example = "645.0") double startSeconds,
      @Schema(description = "끝(초)", example = "694.0") double endSeconds) {}
}
