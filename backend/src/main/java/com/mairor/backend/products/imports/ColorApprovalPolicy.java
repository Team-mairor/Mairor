package com.mairor.backend.products.imports;

import com.mairor.backend.products.entity.ColorSource;
import com.mairor.backend.products.entity.ReviewStatus;
import com.mairor.backend.products.imports.CollectedProduct.CollectedColor;
import com.mairor.backend.products.imports.CollectedProduct.ShadeLink;
import java.util.Set;
import org.springframework.stereotype.Component;

/**
 * 수집한 색이 서비스에 쓸 수 있는 색인지 **그때의 설정으로** 판정한다(출처별 판정표). 판정은 저장해 두지 않고 매번 다시 한다. 임계값을 고치면 같은 사진도 다시 통과할
 * 수 있다. 수집기는 {@code shadeLink}·{@code colorQuality} 같은 재료만 보내고 쓸지는 여기서 정한다.
 *
 * <ul>
 *   <li>{@code SOURCE_VALUE}: 켠 사이트의 값이고 호수에 연결돼 있으면(UNVERIFIED 가 아니면) 통과. 품질 임계값은 없다.
 *   <li>{@code SWATCH_CHIP}·{@code PRODUCT_PHOTO}: 연결 근거가 허용 목록({@code OPTION_IMAGE}·{@code
 *       SINGLE_SHADE_PRODUCT}, 켰다면 {@code LABEL_IN_IMAGE})이고 품질이 출처별 임계값 이상.
 *   <li>{@code WEB_PHOTO}: 연결 근거가 {@code OPTION_IMAGE}(그 호수 전용 페이지) 또는 켠 {@code LABEL_IN_IMAGE}이고 웹
 *       사진 임계값 이상.
 *   <li>{@code LLM_ESTIMATE}: 켰을 때만 통과.
 * </ul>
 *
 * 통과하지 못한 색은 {@link ReviewStatus#BELOW_THRESHOLD}로 저장한다. 사람의 검수를 기다리는 상태가 아니다.
 */
@Component
public class ColorApprovalPolicy {

  private static final Set<ShadeLink> PHOTO_LINKS =
      Set.of(ShadeLink.OPTION_IMAGE, ShadeLink.SINGLE_SHADE_PRODUCT);

  private final CatalogColorProperties properties;

  public ColorApprovalPolicy(CatalogColorProperties properties) {
    this.properties = properties;
  }

  /**
   * @param productSource 상품의 {@code source}. 사이트별로 켜는 {@code SOURCE_VALUE} 판정에 쓴다
   * @return 색이 있는 칸의 판정. 색이 없는 칸(hex 가 null)은 {@code null}
   */
  public ReviewStatus judge(String productSource, CollectedColor color) {
    if (!color.hasColor()) {
      return null;
    }
    return passes(productSource, color) ? ReviewStatus.AUTO_APPROVED : ReviewStatus.BELOW_THRESHOLD;
  }

  /**
   * 저장된 색의 출처가 **현재 정책에서 아예 쓸 수 없는 출처**인가의 반대. 저장된 색에는 품질 점수와 연결 근거가 남아 있지 않아서 사진 색의 임계값은 다시 확인할 수
   * 없다(그건 같은 값을 다시 수집해 {@link #judge}로 본다). 저장된 값만으로 알 수 있는 금지는 둘이다: 사이트 색값은 켠 사이트만, 모델 추정은 켰을 때만.
   *
   * @param productSource 상품의 {@code source}
   */
  public boolean isSourceAllowed(String productSource, ColorSource source) {
    return switch (source) {
      case SOURCE_VALUE -> properties.sourceValueSites().contains(productSource);
      case LLM_ESTIMATE -> properties.llmEstimateEnabled();
      case SWATCH_CHIP, PRODUCT_PHOTO, WEB_PHOTO, SAMPLE -> true;
    };
  }

  private boolean passes(String productSource, CollectedColor color) {
    ColorSource source = color.colorSource();
    ShadeLink link = color.shadeLink();
    if (source == null || link == null) {
      return false;
    }
    return switch (source) {
      case SOURCE_VALUE ->
          properties.sourceValueSites().contains(productSource) && link != ShadeLink.UNVERIFIED;
      case SWATCH_CHIP, PRODUCT_PHOTO -> linkAllowed(link, false) && qualityPasses(color);
      case WEB_PHOTO -> linkAllowed(link, true) && qualityPasses(color);
      case LLM_ESTIMATE -> properties.llmEstimateEnabled();
      case SAMPLE -> false;
    };
  }

  /** 웹 사진은 그 호수 전용 페이지의 사진({@code OPTION_IMAGE})만 인정하고, 공식 홈 사진은 호수가 하나뿐인 상품의 사진도 인정한다. */
  private boolean linkAllowed(ShadeLink link, boolean web) {
    if (link == ShadeLink.LABEL_IN_IMAGE) {
      return properties.labelInImageEnabled();
    }
    return web ? link == ShadeLink.OPTION_IMAGE : PHOTO_LINKS.contains(link);
  }

  private boolean qualityPasses(CollectedColor color) {
    Double min = properties.minQuality().get(color.colorSource());
    return min != null && color.colorQuality() != null && color.colorQuality() >= min;
  }
}
