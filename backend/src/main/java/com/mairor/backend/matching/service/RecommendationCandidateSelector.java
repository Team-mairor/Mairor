package com.mairor.backend.matching.service;

import com.mairor.backend.products.imports.ColorDifference;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

/** 색 비교가 가능한 본인 파우치 대체 후보를 거리순으로 최대 3개 선택한다. */
public final class RecommendationCandidateSelector {

  public static final int MAX_CANDIDATES = 3;

  private static final Comparator<RankedCandidate> ORDER =
      Comparator.comparingDouble(RankedCandidate::distance)
          .thenComparing(candidate -> candidate.candidate().pouchItemId());

  /** 색 칸은 사용 가능한 색만 selector에 전달한다. 색상 원천 조회는 호출자가 수행한다. */
  public List<RankedCandidate> select(
      String makeup, String referenceHex, List<Candidate> candidates) {
    if (referenceHex == null || candidates == null || candidates.isEmpty()) {
      return List.of();
    }

    return candidates.stream()
        .filter(candidate -> PouchCompatibilityPolicy.supports(makeup, candidate.typeCode()))
        .map(candidate -> closestColor(candidate, referenceHex))
        .filter(Objects::nonNull)
        .sorted(ORDER)
        .limit(MAX_CANDIDATES)
        .toList();
  }

  private static RankedCandidate closestColor(Candidate candidate, String referenceHex) {
    return candidate.colors().stream()
        .map(
            color ->
                new RankedCandidate(
                    candidate,
                    color.colorId(),
                    color.hex(),
                    ColorDifference.deltaE2000(referenceHex, color.hex())))
        .min(
            Comparator.comparingDouble(RankedCandidate::distance)
                .thenComparing(
                    ranked -> ranked.matchedColorId(),
                    Comparator.nullsFirst(Comparator.naturalOrder())))
        .orElse(null);
  }

  /** 같은 파우치 항목은 원본 제품·호수 ID가 모두 확인될 때만 SAME이다. */
  public static boolean isSame(
      UUID sourceProductId,
      UUID sourceShadeId,
      UUID candidateProductId,
      UUID candidateShadeId) {
    return sourceProductId != null
        && sourceShadeId != null
        && Objects.equals(sourceProductId, candidateProductId)
        && Objects.equals(sourceShadeId, candidateShadeId);
  }

  public record Candidate(
      UUID pouchItemId,
      UUID productId,
      UUID shadeId,
      String categoryCode,
      String typeCode,
      List<ColorOption> colors) {
    public Candidate {
      Objects.requireNonNull(pouchItemId, "pouchItemId");
      Objects.requireNonNull(categoryCode, "categoryCode");
      Objects.requireNonNull(typeCode, "typeCode");
      colors = List.copyOf(Objects.requireNonNull(colors, "colors"));
    }
  }

  /** MANUAL 또는 단색 파우치 색은 colorId=null, 카탈로그 팔레트 색은 색 칸 ID를 가진다. */
  public record ColorOption(UUID colorId, String hex) {
    public ColorOption {
      Objects.requireNonNull(hex, "hex");
    }
  }

  public record RankedCandidate(
      Candidate candidate, UUID matchedColorId, String matchedColorHex, double distance) {}
}
