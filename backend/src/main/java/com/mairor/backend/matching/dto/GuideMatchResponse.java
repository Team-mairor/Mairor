package com.mairor.backend.matching.dto;

import com.mairor.backend.matching.entity.GuideMatch;
import java.time.Instant;
import java.util.UUID;
import tools.jackson.databind.JsonNode;

/** 매칭 생성 응답. steps는 생성 시 저장한 JSON 스냅샷 그대로다. */
public record GuideMatchResponse(
    UUID matchId,
    UUID guideId,
    int guideVersion,
    long pouchVersion,
    int referenceVersion,
    Instant createdAt,
    JsonNode steps) {

  public static GuideMatchResponse from(GuideMatch match, JsonNode steps) {
    return new GuideMatchResponse(
        match.getId(),
        match.getGuideId(),
        match.getGuideVersion(),
        match.getPouchVersion(),
        match.getReferenceVersion(),
        match.getCreatedAt(),
        steps);
  }
}
