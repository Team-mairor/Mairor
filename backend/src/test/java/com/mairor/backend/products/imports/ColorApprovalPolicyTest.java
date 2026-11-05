package com.mairor.backend.products.imports;

import static com.mairor.backend.products.imports.ImportTestData.color;
import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.products.entity.ColorSource;
import com.mairor.backend.products.entity.NameSource;
import com.mairor.backend.products.entity.ReviewStatus;
import com.mairor.backend.products.imports.CollectedProduct.CollectedColor;
import com.mairor.backend.products.imports.CollectedProduct.ShadeLink;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

/** 출처별 자동 사용 판정표. 설정에 따라 같은 색이 통과하기도 하고 못 하기도 한다. */
class ColorApprovalPolicyTest {

  private static final String SITE = "OFFICIAL:3ce.example";

  private static ColorApprovalPolicy policy(
      Map<ColorSource, Double> min, boolean label, Set<String> sites, boolean llm) {
    return new ColorApprovalPolicy(new CatalogColorProperties(min, label, sites, llm, 5.0));
  }

  private static CollectedColor photo(ColorSource source, ShadeLink link, Double quality) {
    return color(1, null, NameSource.NONE, "#C9707A", source, link, quality);
  }

  private static final Map<ColorSource, Double> THRESHOLDS =
      Map.of(
          ColorSource.SWATCH_CHIP, 0.8,
          ColorSource.PRODUCT_PHOTO, 0.8,
          ColorSource.WEB_PHOTO, 0.9);

  @Test
  void nothingPassesBeforeThresholdsAreSet() {
    ColorApprovalPolicy none = policy(Map.of(), false, Set.of(), false);

    for (ColorSource source :
        new ColorSource[] {
          ColorSource.SWATCH_CHIP,
          ColorSource.PRODUCT_PHOTO,
          ColorSource.WEB_PHOTO,
          ColorSource.SOURCE_VALUE,
          ColorSource.LLM_ESTIMATE
        }) {
      assertThat(none.judge(SITE, photo(source, ShadeLink.OPTION_IMAGE, 1.0)))
          .as(source.name())
          .isEqualTo(ReviewStatus.BELOW_THRESHOLD);
    }
  }

  @Test
  void colorlessSlotHasNoJudgement() {
    assertThat(
            policy(THRESHOLDS, true, Set.of(SITE), true).judge(SITE, ImportTestData.colorless(1)))
        .isNull();
  }

  @Test
  void photoColorNeedsAnAllowedLinkAndTheQualityThreshold() {
    ColorApprovalPolicy policy = policy(THRESHOLDS, false, Set.of(), false);

    assertThat(policy.judge(SITE, photo(ColorSource.PRODUCT_PHOTO, ShadeLink.OPTION_IMAGE, 0.8)))
        .isEqualTo(ReviewStatus.AUTO_APPROVED);
    assertThat(
            policy.judge(
                SITE, photo(ColorSource.SWATCH_CHIP, ShadeLink.SINGLE_SHADE_PRODUCT, 0.95)))
        .isEqualTo(ReviewStatus.AUTO_APPROVED);
    assertThat(policy.judge(SITE, photo(ColorSource.PRODUCT_PHOTO, ShadeLink.OPTION_IMAGE, 0.79)))
        .isEqualTo(ReviewStatus.BELOW_THRESHOLD);
    // 연결 근거가 없으면 품질이 아무리 좋아도 쓰지 않는다 (다른 호수의 사진일 수 있다)
    assertThat(policy.judge(SITE, photo(ColorSource.PRODUCT_PHOTO, ShadeLink.UNVERIFIED, 1.0)))
        .isEqualTo(ReviewStatus.BELOW_THRESHOLD);
  }

  @Test
  void labelInImageIsOffUntilEnabled() {
    CollectedColor labeled = photo(ColorSource.PRODUCT_PHOTO, ShadeLink.LABEL_IN_IMAGE, 0.95);

    assertThat(policy(THRESHOLDS, false, Set.of(), false).judge(SITE, labeled))
        .isEqualTo(ReviewStatus.BELOW_THRESHOLD);
    assertThat(policy(THRESHOLDS, true, Set.of(), false).judge(SITE, labeled))
        .isEqualTo(ReviewStatus.AUTO_APPROVED);
  }

  @Test
  void webPhotoHasItsOwnThresholdAndOnlyAcceptsTheShadesOwnPage() {
    ColorApprovalPolicy policy = policy(THRESHOLDS, true, Set.of(), false);

    assertThat(policy.judge(SITE, photo(ColorSource.WEB_PHOTO, ShadeLink.OPTION_IMAGE, 0.9)))
        .isEqualTo(ReviewStatus.AUTO_APPROVED);
    assertThat(policy.judge(SITE, photo(ColorSource.WEB_PHOTO, ShadeLink.OPTION_IMAGE, 0.85)))
        .isEqualTo(ReviewStatus.BELOW_THRESHOLD);
    assertThat(policy.judge(SITE, photo(ColorSource.WEB_PHOTO, ShadeLink.LABEL_IN_IMAGE, 0.95)))
        .isEqualTo(ReviewStatus.AUTO_APPROVED);
    // 호수가 하나뿐인 상품의 사진은 공식 홈 사진에만 인정한다
    assertThat(
            policy.judge(SITE, photo(ColorSource.WEB_PHOTO, ShadeLink.SINGLE_SHADE_PRODUCT, 0.99)))
        .isEqualTo(ReviewStatus.BELOW_THRESHOLD);
  }

  @Test
  void sourceValueIsUsedOnlyForSitesThatWereTurnedOnAndWhenLinked() {
    CollectedColor value =
        color(
            1,
            null,
            NameSource.NONE,
            "#C9707A",
            ColorSource.SOURCE_VALUE,
            ShadeLink.OPTION_IMAGE,
            null);
    CollectedColor unlinked =
        color(
            1,
            null,
            NameSource.NONE,
            "#C9707A",
            ColorSource.SOURCE_VALUE,
            ShadeLink.UNVERIFIED,
            null);
    ColorApprovalPolicy on = policy(Map.of(), false, Set.of(SITE), false);

    assertThat(on.judge(SITE, value)).isEqualTo(ReviewStatus.AUTO_APPROVED);
    assertThat(on.judge("OFFICIAL:other.example", value)).isEqualTo(ReviewStatus.BELOW_THRESHOLD);
    assertThat(on.judge(SITE, unlinked)).isEqualTo(ReviewStatus.BELOW_THRESHOLD);
    // 품질 임계값은 적용하지 않는다
    assertThat(on.judge(SITE, value)).isEqualTo(ReviewStatus.AUTO_APPROVED);
  }

  @Test
  void llmEstimateIsOffByDefault() {
    CollectedColor estimate =
        color(
            1,
            null,
            NameSource.NONE,
            "#C9707A",
            ColorSource.LLM_ESTIMATE,
            ShadeLink.UNVERIFIED,
            null);

    assertThat(policy(THRESHOLDS, true, Set.of(SITE), false).judge(SITE, estimate))
        .isEqualTo(ReviewStatus.BELOW_THRESHOLD);
    assertThat(policy(THRESHOLDS, true, Set.of(SITE), true).judge(SITE, estimate))
        .isEqualTo(ReviewStatus.AUTO_APPROVED);
  }

  @Test
  void changingTheThresholdChangesTheJudgementOfTheSamePhoto() {
    CollectedColor sameCollectedPhoto =
        photo(ColorSource.PRODUCT_PHOTO, ShadeLink.OPTION_IMAGE, 0.7);

    assertThat(
            policy(Map.of(ColorSource.PRODUCT_PHOTO, 0.8), false, Set.of(), false)
                .judge(SITE, sameCollectedPhoto))
        .isEqualTo(ReviewStatus.BELOW_THRESHOLD);
    assertThat(
            policy(Map.of(ColorSource.PRODUCT_PHOTO, 0.6), false, Set.of(), false)
                .judge(SITE, sameCollectedPhoto))
        .isEqualTo(ReviewStatus.AUTO_APPROVED);
  }

  @Test
  void storedColorsAreCheckedAgainstWhatTheSourceAloneForbids() {
    ColorApprovalPolicy off = policy(THRESHOLDS, true, Set.of(), false);
    ColorApprovalPolicy on = policy(THRESHOLDS, true, Set.of(SITE), true);

    // 사이트 색값은 켠 사이트만, 모델 추정은 켰을 때만. 사진 색의 임계값은 저장된 값만으로 다시 볼 수 없다
    assertThat(off.isSourceAllowed(SITE, ColorSource.SOURCE_VALUE)).isFalse();
    assertThat(off.isSourceAllowed(SITE, ColorSource.LLM_ESTIMATE)).isFalse();
    assertThat(on.isSourceAllowed(SITE, ColorSource.SOURCE_VALUE)).isTrue();
    assertThat(on.isSourceAllowed("OFFICIAL:other.example", ColorSource.SOURCE_VALUE)).isFalse();
    assertThat(on.isSourceAllowed(SITE, ColorSource.LLM_ESTIMATE)).isTrue();
    for (ColorSource photo :
        new ColorSource[] {
          ColorSource.SWATCH_CHIP, ColorSource.PRODUCT_PHOTO, ColorSource.WEB_PHOTO
        }) {
      assertThat(off.isSourceAllowed(SITE, photo)).as(photo.name()).isTrue();
    }
  }
}
