package com.mairor.backend.matching.dto;

import com.mairor.backend.matching.entity.GuideMatch;
import java.time.Instant;
import java.util.UUID;
import tools.jackson.databind.JsonNode;

/** 조회 응답은 생성 시점의 결과를 유지하고 현재 데이터와 다르면 stale만 표시한다. */
public record GuideMatchDetailResponse(
    UUID matchId,
    UUID guideId,
    int guideVersion,
    long pouchVersion,
    int referenceVersion,
    Instant createdAt,
    JsonNode steps,
    boolean stale) {

  public static GuideMatchDetailResponse from(GuideMatch match, JsonNode steps, boolean stale) {
    return new GuideMatchDetailResponse(
        match.getId(),
        match.getGuideId(),
        match.getGuideVersion(),
        match.getPouchVersion(),
        match.getReferenceVersion(),
        match.getCreatedAt(),
        steps,
        stale);
  }
}
