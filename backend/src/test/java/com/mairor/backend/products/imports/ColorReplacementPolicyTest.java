package com.mairor.backend.products.imports;

import static com.mairor.backend.products.imports.ImportTestData.T0;
import static com.mairor.backend.products.imports.ImportTestData.T1;
import static com.mairor.backend.products.imports.ImportTestData.T2;
import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.products.entity.ColorSource;
import com.mairor.backend.products.entity.NameSource;
import com.mairor.backend.products.entity.ProductShadeColor;
import com.mairor.backend.products.entity.ReviewStatus;
import com.mairor.backend.products.imports.CollectedProduct.CollectedColor;
import com.mairor.backend.products.imports.CollectedProduct.ColorStatus;
import com.mairor.backend.products.imports.CollectedProduct.ShadeLink;
import com.mairor.backend.products.imports.ColorReplacementPolicy.Decision;
import com.mairor.backend.products.imports.ColorReplacementPolicy.Result;
import java.time.Instant;
import org.junit.jupiter.api.Test;

/** 칸 하나에 이미 있는 색과 새 색 중 어느 쪽을 쓸지. 좋은 값을 나쁜 값으로 낮추지 않고, 사람이 정한 값은 덮지 않는다. */
class ColorReplacementPolicyTest {

  private static ProductShadeColor existing(
      String hex, ColorSource source, ReviewStatus status, Instant collectedAt) {
    return ImportTestData.slot(
        ImportTestData.shade("01"), 1, null, NameSource.NONE, hex, source, status, collectedAt);
  }

  private static CollectedColor incoming(String hex, ColorSource source) {
    return ImportTestData.color(1, null, NameSource.NONE, hex, source, ShadeLink.OPTION_IMAGE, 0.9);
  }

  private static Result decide(
      ProductShadeColor existing,
      CollectedColor incoming,
      ReviewStatus judged,
      ColorStatus status,
      Instant at) {
    return ColorReplacementPolicy.decide(existing, incoming, judged, status, at);
  }

  private static final ReviewStatus AUTO = ReviewStatus.AUTO_APPROVED;
  private static final ReviewStatus BELOW = ReviewStatus.BELOW_THRESHOLD;

  // --- 수집 결과가 비었거나 실패 ---

  @Test
  void failedExtractionNeverTouchesTheExistingColor() {
    ProductShadeColor old = existing("#111111", ColorSource.PRODUCT_PHOTO, AUTO, T1);

    Result result =
        decide(old, incoming("#222222", ColorSource.PRODUCT_PHOTO), AUTO, ColorStatus.FAILED, T2);

    assertThat(result.decision()).isEqualTo(Decision.KEPT_ON_FAILURE);
    assertThat(result.status()).isEqualTo(AUTO);
    assertThat(result.decision().changesColor()).isFalse();
  }

  @Test
  void notFoundOrColorlessSlotKeepsTheExistingColor() {
    ProductShadeColor old = existing("#111111", ColorSource.PRODUCT_PHOTO, AUTO, T1);

    assertThat(decide(old, ImportTestData.colorless(1), null, ColorStatus.NOT_FOUND, T2).decision())
        .isEqualTo(Decision.KEPT_NOT_FOUND);
    // 호수에 다른 칸은 색이 나왔지만 이 칸만 색이 없다
    assertThat(decide(old, ImportTestData.colorless(1), null, ColorStatus.EXTRACTED, T2).decision())
        .isEqualTo(Decision.KEPT_NOT_FOUND);
  }

  // --- 기존 색이 없거나 쓸 수 없음 ---

  @Test
  void newSlotOrSlotWithoutColorAdoptsTheJudgedValue() {
    CollectedColor value = incoming("#222222", ColorSource.PRODUCT_PHOTO);

    Result fresh = decide(null, value, AUTO, ColorStatus.EXTRACTED, T2);
    Result belowFresh = decide(null, value, BELOW, ColorStatus.EXTRACTED, T2);
    Result emptySlot =
        decide(existing(null, null, null, null), value, AUTO, ColorStatus.EXTRACTED, T2);

    assertThat(fresh).isEqualTo(new Result(Decision.ADOPT, AUTO));
    assertThat(belowFresh).isEqualTo(new Result(Decision.ADOPT, BELOW));
    assertThat(emptySlot).isEqualTo(new Result(Decision.ADOPT, AUTO));
    assertThat(fresh.decision().changesColor()).isTrue();
  }

  @Test
  void unusableExistingColorIsReplacedByTheNewValueEvenIfItIsStillUnusable() {
    ProductShadeColor old = existing("#111111", ColorSource.PRODUCT_PHOTO, BELOW, T1);

    assertThat(
            decide(
                old,
                incoming("#222222", ColorSource.PRODUCT_PHOTO),
                AUTO,
                ColorStatus.EXTRACTED,
                T2))
        .isEqualTo(new Result(Decision.ADOPT, AUTO));
    assertThat(
            decide(
                old,
                incoming("#222222", ColorSource.PRODUCT_PHOTO),
                BELOW,
                ColorStatus.EXTRACTED,
                T2))
        .isEqualTo(new Result(Decision.ADOPT, BELOW));
  }

  // --- 사람이 정한 값, 오래된 수집 ---

  @Test
  void operatorDecisionsAreNeverOverwrittenByCollection() {
    for (ReviewStatus status : new ReviewStatus[] {ReviewStatus.APPROVED, ReviewStatus.REJECTED}) {
      ProductShadeColor old = existing("#111111", ColorSource.WEB_PHOTO, status, T1);

      Result result =
          decide(
              old, incoming("#222222", ColorSource.SOURCE_VALUE), AUTO, ColorStatus.EXTRACTED, T2);

      assertThat(result.decision()).as(status.name()).isEqualTo(Decision.KEPT_OPERATOR);
      assertThat(result.status()).isEqualTo(status);
    }
  }

  @Test
  void aCollectionOlderThanTheStoredColorDoesNotReplaceIt() {
    ProductShadeColor old = existing("#111111", ColorSource.PRODUCT_PHOTO, AUTO, T2);

    assertThat(
            decide(
                    old,
                    incoming("#222222", ColorSource.SOURCE_VALUE),
                    AUTO,
                    ColorStatus.EXTRACTED,
                    T1)
                .decision())
        .isEqualTo(Decision.KEPT_STALE);
  }

  // --- 사용 중인 색과 새 값 ---

  @Test
  void sameValueIsUnchanged() {
    ProductShadeColor old = existing("#111111", ColorSource.PRODUCT_PHOTO, AUTO, T1);

    assertThat(
            decide(
                    old,
                    incoming("#111111", ColorSource.PRODUCT_PHOTO),
                    AUTO,
                    ColorStatus.EXTRACTED,
                    T2)
                .decision())
        .isEqualTo(Decision.UNCHANGED);
  }

  @Test
  void aGoodColorIsNotLoweredByANewValueThatFailsTheCriteria() {
    ProductShadeColor old = existing("#111111", ColorSource.PRODUCT_PHOTO, AUTO, T1);

    Result result =
        decide(
            old, incoming("#222222", ColorSource.PRODUCT_PHOTO), BELOW, ColorStatus.EXTRACTED, T2);

    assertThat(result).isEqualTo(new Result(Decision.KEPT_BETTER, AUTO));
  }

  @Test
  void higherPrioritySourceThatPassesReplacesALowerOne() {
    ProductShadeColor old = existing("#111111", ColorSource.WEB_PHOTO, AUTO, T1);

    Result result =
        decide(
            old, incoming("#222222", ColorSource.PRODUCT_PHOTO), AUTO, ColorStatus.EXTRACTED, T2);

    assertThat(result).isEqualTo(new Result(Decision.REPLACE, AUTO));
    assertThat(result.decision().changesColor()).isTrue();
  }

  @Test
  void lowerPrioritySourceNeverReplacesAHigherOne() {
    ProductShadeColor old = existing("#111111", ColorSource.PRODUCT_PHOTO, AUTO, T1);

    assertThat(
            decide(old, incoming("#222222", ColorSource.WEB_PHOTO), AUTO, ColorStatus.EXTRACTED, T2)
                .decision())
        .isEqualTo(Decision.KEPT_BETTER);
    assertThat(
            decide(
                    old,
                    incoming("#222222", ColorSource.LLM_ESTIMATE),
                    AUTO,
                    ColorStatus.EXTRACTED,
                    T2)
                .decision())
        .isEqualTo(Decision.KEPT_BETTER);
  }

  @Test
  void theFivePrioritiesFollowThePolicyOrder() {
    ColorSource[] order = {
      ColorSource.SOURCE_VALUE,
      ColorSource.SWATCH_CHIP,
      ColorSource.PRODUCT_PHOTO,
      ColorSource.WEB_PHOTO,
      ColorSource.LLM_ESTIMATE
    };
    for (int i = 0; i < order.length; i++) {
      for (int j = 0; j < order.length; j++) {
        if (i == j) {
          continue;
        }
        ProductShadeColor old = existing("#111111", order[j], AUTO, T1);
        Decision expected = i < j ? Decision.REPLACE : Decision.KEPT_BETTER;

        assertThat(
                decide(old, incoming("#222222", order[i]), AUTO, ColorStatus.EXTRACTED, T2)
                    .decision())
            .as(order[i] + " vs existing " + order[j])
            .isEqualTo(expected);
      }
    }
  }

  @Test
  void samePriorityIsReplacedOnlyByANewerCollection() {
    ProductShadeColor old = existing("#111111", ColorSource.PRODUCT_PHOTO, AUTO, T1);
    CollectedColor changed = incoming("#222222", ColorSource.PRODUCT_PHOTO);

    assertThat(decide(old, changed, AUTO, ColorStatus.EXTRACTED, T2).decision())
        .isEqualTo(Decision.REPLACE);
    // 같은 수집 시각은 더 최신이 아니다
    assertThat(decide(old, changed, AUTO, ColorStatus.EXTRACTED, T1).decision())
        .isEqualTo(Decision.KEPT_BETTER);
  }

  @Test
  void existingColorWithoutCollectionTimeIsReplacedByTheSamePriorityNewValue() {
    ProductShadeColor old = existing("#111111", ColorSource.PRODUCT_PHOTO, AUTO, null);

    assertThat(
            decide(
                    old,
                    incoming("#222222", ColorSource.PRODUCT_PHOTO),
                    AUTO,
                    ColorStatus.EXTRACTED,
                    T0)
                .decision())
        .isEqualTo(Decision.REPLACE);
  }

  // --- 현재 정책으로 쓸 수 없게 된 색 ---

  private static Result decideWithSourceAllowed(
      ProductShadeColor existing,
      CollectedColor incoming,
      ReviewStatus judged,
      ColorStatus status,
      Instant at,
      boolean allowed) {
    return ColorReplacementPolicy.decide(existing, incoming, judged, status, at, allowed);
  }

  @Test
  void aColorWhoseSourceIsNoLongerAllowedIsDowngradedEvenIfTheCollectionFailedOrIsStale() {
    ProductShadeColor old = existing("#111111", ColorSource.SOURCE_VALUE, AUTO, T1);

    Result failed =
        decideWithSourceAllowed(
            old,
            incoming("#111111", ColorSource.SOURCE_VALUE),
            AUTO,
            ColorStatus.FAILED,
            T2,
            false);
    Result notFound =
        decideWithSourceAllowed(
            old, ImportTestData.colorless(1), null, ColorStatus.NOT_FOUND, T2, false);
    // 오래된 수집이 늦게 와도 '이 출처는 이제 못 쓴다'는 정책은 그대로 적용된다
    Result stale =
        decideWithSourceAllowed(
            old,
            incoming("#222222", ColorSource.SOURCE_VALUE),
            BELOW,
            ColorStatus.EXTRACTED,
            T0,
            false);

    for (Result result : new Result[] {failed, notFound, stale}) {
      assertThat(result).isEqualTo(new Result(Decision.DOWNGRADE, BELOW));
    }
    assertThat(Decision.DOWNGRADE.changesColor()).isTrue();
  }

  @Test
  void aColorWhoseSourceIsNoLongerAllowedIsReplacedByTheFreshJudgedValue() {
    ProductShadeColor old = existing("#111111", ColorSource.SOURCE_VALUE, AUTO, T1);

    // 같은 값을 다시 받아도 UNCHANGED 로 끝내지 않는다. 현재 정책의 판정이 저장된다
    Result result =
        decideWithSourceAllowed(
            old,
            incoming("#111111", ColorSource.SOURCE_VALUE),
            BELOW,
            ColorStatus.EXTRACTED,
            T2,
            false);

    assertThat(result).isEqualTo(new Result(Decision.ADOPT, BELOW));
  }

  @Test
  void operatorDecisionsAreNotDowngradedByPolicyChanges() {
    ProductShadeColor old =
        existing("#111111", ColorSource.SOURCE_VALUE, ReviewStatus.APPROVED, T1);

    assertThat(
            decideWithSourceAllowed(
                    old, ImportTestData.colorless(1), null, ColorStatus.FAILED, T2, false)
                .decision())
        .isEqualTo(Decision.KEPT_ON_FAILURE);
    assertThat(
            decideWithSourceAllowed(
                    old,
                    incoming("#222222", ColorSource.SOURCE_VALUE),
                    AUTO,
                    ColorStatus.EXTRACTED,
                    T2,
                    false)
                .decision())
        .isEqualTo(Decision.KEPT_OPERATOR);
  }

  @Test
  void aNewImageThatFailsTheCriteriaNeverLowersAnExistingColorEvenWithTheSameHex() {
    ProductShadeColor old = existing("#111111", ColorSource.PRODUCT_PHOTO, AUTO, T1);

    // 같은 HEX·출처라도 같은 이미지라는 보장이 없다. 다른 사진에서 같은 값이 나왔는데 연결 근거나 품질이 부족하다고 해서
    // 쓰던 정상 색을 내리지 않는다
    assertThat(
            decide(
                old,
                incoming("#111111", ColorSource.PRODUCT_PHOTO),
                BELOW,
                ColorStatus.EXTRACTED,
                T2))
        .isEqualTo(new Result(Decision.UNCHANGED, AUTO));
    // 다른 값이 낮은 품질로 와도 좋은 값을 낮추지 않고 기존 색을 지킨다
    assertThat(
            decide(
                old,
                incoming("#222222", ColorSource.PRODUCT_PHOTO),
                BELOW,
                ColorStatus.EXTRACTED,
                T2))
        .isEqualTo(new Result(Decision.KEPT_BETTER, AUTO));
  }

  @Test
  void anAllowedSourceBehavesAsBefore() {
    ProductShadeColor old = existing("#111111", ColorSource.SOURCE_VALUE, AUTO, T1);

    assertThat(
            decideWithSourceAllowed(
                    old,
                    incoming("#111111", ColorSource.SOURCE_VALUE),
                    AUTO,
                    ColorStatus.EXTRACTED,
                    T2,
                    true)
                .decision())
        .isEqualTo(Decision.UNCHANGED);
  }
}
