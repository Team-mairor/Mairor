package com.mairor.backend.matching.service;

import com.mairor.backend.products.imports.ColorDifference;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.UUID;
import org.springframework.stereotype.Component;

/** 색이 있는 본인 파우치 대체 후보를 거리순으로 고른다. 자동 추천은 최대 3개다. */
@Component
public final class RecommendationCandidateSelector {

  public static final int MAX_CANDIDATES = 3;

  private static final Comparator<RankedCandidate> ORDER =
      Comparator.comparingDouble(RankedCandidate::distance)
          .thenComparing(candidate -> candidate.candidate().pouchItemId());

  /** 색 칸은 사용 가능한 색만 selector에 전달한다. 색상 원천 조회는 호출자가 수행한다. */
  public List<RankedCandidate> select(
      String makeup, String referenceHex, List<Candidate> candidates) {
    return selectAll(makeup, referenceHex, candidates).stream().limit(MAX_CANDIDATES).toList();
  }

  /**
   * 호환되는 종류이고 쓸 수 있는 색이 있는 모든 항목을 반환한다. 교체 목록도 같은 서버 판정을 쓴다.
   *
   * <p>기준색이 있으면 색차(CIEDE2000)가 가까운 순이고 색차 상한은 없다. 기준색이 없으면 비교할 수 없으므로 받은 순서(파우치 순서)를 그대로 둔다.
   */
  public List<RankedCandidate> selectAll(
      String makeup, String referenceHex, List<Candidate> candidates) {
    if (candidates == null || candidates.isEmpty()) {
      return List.of();
    }

    var compatible =
        candidates.stream()
            .filter(candidate -> PouchCompatibilityPolicy.supports(makeup, candidate.typeCode()))
            .map(
                candidate ->
                    referenceHex == null
                        ? firstColor(candidate)
                        : closestColor(candidate, referenceHex))
            .filter(Objects::nonNull);
    return referenceHex == null ? compatible.toList() : compatible.sorted(ORDER).toList();
  }

  private static RankedCandidate firstColor(Candidate candidate) {
    return candidate.colors().stream()
        .findFirst()
        .map(color -> new RankedCandidate(candidate, color.colorId(), color.hex(), 0.0))
        .orElse(null);
  }

  /** 실행의 수동 선택은 호출자가 같은 카테고리를 검사한 뒤 이 색 칸 선택만 재사용한다. */
  public static RankedCandidate closestColor(Candidate candidate, String referenceHex) {
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
      UUID sourceProductId, UUID sourceShadeId, UUID candidateProductId, UUID candidateShadeId) {
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
