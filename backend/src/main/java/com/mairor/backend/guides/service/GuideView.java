package com.mairor.backend.guides.service;

import com.mairor.backend.guides.entity.Guide;
import com.mairor.backend.guides.entity.ReviewStatus;
import java.time.Instant;
import java.util.UUID;

/** 가이드 한 건(검수 결정의 결과). JSON 칸(입력·설명·영역)은 저장된 문자열 그대로다. */
public record GuideView(
    UUID guideId,
    UUID analysisJobId,
    String youtubeVideoId,
    int version,
    ReviewStatus reviewStatus,
    String meshVersion,
    String framesManifestKey,
    Instant reviewedAt,
    Instant createdAt,
    String guideInput,
    String explanation,
    String area) {

  static GuideView of(Guide guide) {
    return new GuideView(
        guide.getId(),
        guide.getAnalysisJob().getId(),
        guide.getVideo().getYoutubeVideoId(),
        guide.getVersion(),
        guide.getReviewStatus(),
        guide.getMeshVersion(),
        guide.getFramesManifestKey(),
        guide.getReviewedAt(),
        guide.getCreatedAt(),
        guide.getGuideInput(),
        guide.getExplanation(),
        guide.getArea());
  }
}
