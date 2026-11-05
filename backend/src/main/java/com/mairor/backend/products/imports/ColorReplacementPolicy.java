package com.mairor.backend.products.imports;

import com.mairor.backend.products.entity.ColorSource;
import com.mairor.backend.products.entity.ProductShadeColor;
import com.mairor.backend.products.entity.ReviewStatus;
import com.mairor.backend.products.imports.CollectedProduct.CollectedColor;
import com.mairor.backend.products.imports.CollectedProduct.ColorStatus;
import java.time.Instant;
import java.util.Objects;

/**
 * 칸 하나에 이미 있는 색과 새로 수집한 색 중 어느 쪽을 쓸지 정한다. 좋은 값을 나쁜 값으로 낮추지 않고, 사람이 정한 값은 수집이 덮지 않는다.
 *
 * <ol>
 *   <li>수집이 실패했으면({@code FAILED}) 유지, 색을 못 찾았으면({@code NOT_FOUND}이거나 이 칸에 색이 없으면) 유지
 *   <li>기존 색이 운영 정정({@code APPROVED}·{@code REJECTED})이면 유지. 정책이 바뀌어도 수집이 건드리지 않는다
 *   <li>기존 색이 더 최근에 수집됐으면 유지(오래된 수집이 늦게 도착한 경우)
 *   <li>기존 색이 없거나 쓸 수 없으면({@code BELOW_THRESHOLD}) 새 값을 판정해서 채택(쓸 수 없는 값이어도 최신 값으로 갱신)
 *   <li>기존 색이 사용 중이면: 같은 값(HEX·출처)이면 판정과 상관없이 그대로. 다른 값이면 새 값이 통과하지 못했을 때 유지(좋은 값을 낮추지 않는다), 통과했다면
 *       출처 우선순위가 더 높으면 교체, 같으면 더 최신 수집일 때 교체, 낮으면 유지
 * </ol>
 *
 * 기존 색의 출처가 현재 정책에서 쓸 수 없는 출처가 됐으면(사이트 색값을 끈 사이트, 꺼진 모델 추정) 그 색은 이미 쓸 수 없는 색으로 본다. 이것은 저장된 출처만으로 알
 * 수 있는 금지라서 새 수집의 품질과 상관없이 적용한다. 수집이 실패했거나 오래된 수집이어도 사용 불가로 내린다.
 *
 * <p>반대로 **새 이미지의 품질이나 연결 근거가 부족하다는 이유로 기존 색을 내리지 않는다.** 저장된 색에는 이미지 해시·품질·연결 근거가 남아 있지 않아서, 같은
 * HEX가 다시 나와도 같은 근거인지 확인할 수 없다. 사진 색의 임계값이 올라간 경우의 재판정은 실행 결과 파일의 근거와 대조할 수 있는 일괄
 * 재판정(S15P31A306-295)이 한다.
 */
public final class ColorReplacementPolicy {

  /** 칸 하나의 처리 결과. */
  public enum Decision {
    /** 새 값을 채택한다(기존 색이 없거나 쓸 수 없었다). 저장할 승인 상태는 판정 결과다. */
    ADOPT,
    /** 쓰던 색을 더 좋거나 더 최신인 새 값으로 바꾼다. */
    REPLACE,
    /** 같은 값이라 바꿀 것이 없다. */
    UNCHANGED,
    /** 새 값이 통과하지 못했거나 우선순위가 낮아 기존 색을 쓴다. */
    KEPT_BETTER,
    /** 쓰던 색이 현재 정책으로는 쓸 수 없어 사용 불가({@code BELOW_THRESHOLD})로 내린다. 값은 남긴다. */
    DOWNGRADE,
    /** 운영 정정 값이라 덮지 않는다. */
    KEPT_OPERATOR,
    /** 수집이 실패했다. */
    KEPT_ON_FAILURE,
    /** 근거가 되는 이미지나 값을 못 찾았다. */
    KEPT_NOT_FOUND,
    /** 기존 색이 더 최근에 수집됐다. */
    KEPT_STALE;

    /**
     * 이 칸의 저장된 색이나 승인 상태가 바뀌는가. 서비스에 보이는 색이 바뀌면 파우치·가이드 버전이 오른다. 사용 중이던 색을 사용 불가로 내리는 것도 보이는 색이 바뀌는
     * 것이다.
     */
    public boolean changesColor() {
      return this == ADOPT || this == REPLACE || this == DOWNGRADE;
    }
  }

  /**
   * @param decision 처리
   * @param status 처리 뒤 저장할 승인 상태. 색이 바뀌지 않으면 기존 상태, 색이 없으면 {@code null}
   */
  public record Result(Decision decision, ReviewStatus status) {}

  private ColorReplacementPolicy() {}

  /**
   * @param existing 기존 칸. 새로 만드는 칸이면 {@code null}
   * @param incoming 새 수집 칸
   * @param judged {@link ColorApprovalPolicy#judge}의 결과. 새 칸에 색이 없으면 {@code null}
   * @param shadeStatus 이 호수의 색 추출 결과
   * @param incomingCollectedAt 새 수집 시각
   */
  public static Result decide(
      ProductShadeColor existing,
      CollectedColor incoming,
      ReviewStatus judged,
      ColorStatus shadeStatus,
      Instant incomingCollectedAt) {
    return decide(existing, incoming, judged, shadeStatus, incomingCollectedAt, true);
  }

  /**
   * @param existingSourceAllowed 기존 색의 출처가 현재 정책에서 쓸 수 있는 출처인가({@link
   *     ColorApprovalPolicy#isSourceAllowed}). 새로 만드는 칸이나 색이 없는 칸이면 무시한다
   */
  public static Result decide(
      ProductShadeColor existing,
      CollectedColor incoming,
      ReviewStatus judged,
      ColorStatus shadeStatus,
      Instant incomingCollectedAt,
      boolean existingSourceAllowed) {
    ReviewStatus existingStatus = existing == null ? null : existing.getReviewStatus();
    boolean hasExisting = existing != null && existing.getColor() != null;
    // 쓰던 색인데 그 출처가 이제 정책에서 쓸 수 없는 출처다. 새 이미지 품질이 낮아서 기존 색을 지키는 것과 다르다
    boolean forbidden =
        hasExisting
            && existingStatus.isUsable()
            && !existingStatus.isOperatorDecision()
            && !existingSourceAllowed;

    if (shadeStatus == ColorStatus.FAILED) {
      return forbidden ? downgrade() : keep(Decision.KEPT_ON_FAILURE, existingStatus);
    }
    if (shadeStatus == ColorStatus.NOT_FOUND || !incoming.hasColor()) {
      return forbidden ? downgrade() : keep(Decision.KEPT_NOT_FOUND, existingStatus);
    }
    if (!hasExisting) {
      return new Result(Decision.ADOPT, judged);
    }
    if (existingStatus.isOperatorDecision()) {
      return keep(Decision.KEPT_OPERATOR, existingStatus);
    }
    Instant existingAt = existing.getSourceCollectedAt();
    boolean stale =
        existingAt != null
            && incomingCollectedAt != null
            && existingAt.isAfter(incomingCollectedAt);
    if (forbidden) {
      return stale ? downgrade() : new Result(Decision.ADOPT, judged);
    }
    if (stale) {
      return keep(Decision.KEPT_STALE, existingStatus);
    }
    if (!existingStatus.isUsable()) {
      return new Result(Decision.ADOPT, judged);
    }
    if (sameValue(existing, incoming)) {
      // 같은 HEX·출처라도 같은 이미지라는 보장이 없다. 다른 사진에서 같은 값이 나온 것일 수 있고, 새 근거가 기준 미달이라는
      // 이유로 쓰던 정상 색을 내리면 안 된다
      return keep(Decision.UNCHANGED, existingStatus);
    }
    if (judged != ReviewStatus.AUTO_APPROVED) {
      return keep(Decision.KEPT_BETTER, existingStatus);
    }
    ColorSource existingSource = existing.getColorSource();
    ColorSource incomingSource = incoming.colorSource();
    if (incomingSource.outranks(existingSource)) {
      return new Result(Decision.REPLACE, judged);
    }
    if (incomingSource == existingSource && isNewer(incomingCollectedAt, existingAt)) {
      return new Result(Decision.REPLACE, judged);
    }
    return keep(Decision.KEPT_BETTER, existingStatus);
  }

  private static boolean sameValue(ProductShadeColor existing, CollectedColor incoming) {
    return Objects.equals(existing.getColor().getHex(), incoming.hex())
        && existing.getColorSource() == incoming.colorSource();
  }

  private static boolean isNewer(Instant incoming, Instant existing) {
    return incoming != null && (existing == null || incoming.isAfter(existing));
  }

  private static Result keep(Decision decision, ReviewStatus status) {
    return new Result(decision, status);
  }

  private static Result downgrade() {
    return new Result(Decision.DOWNGRADE, ReviewStatus.BELOW_THRESHOLD);
  }
}
