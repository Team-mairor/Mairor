package com.mairor.backend.products.imports;

import com.mairor.backend.products.entity.ColorSource;
import java.util.Map;
import java.util.Set;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * 수집한 색을 서비스에 써도 되는지 정하는 설정({@code catalog.color}). 기본값은 **아무 색도 통과시키지 않는 쪽**이다. 임계값은 기준 세트 리포트로 정한
 * 뒤에 채우고, 그 전에는 사진에서 뽑은 색이 모두 {@code BELOW_THRESHOLD}(서비스에는 null)가 된다. 이 확정은 초기 데이터 운영
 * 적재(S15P31A306-317)의 선행 조건이다.
 *
 * @param minQuality 사진에서 얻은 색의 출처별 최소 품질({@code SWATCH_CHIP}·{@code PRODUCT_PHOTO}·{@code
 *     WEB_PHOTO}). 값이 없는 출처는 통과하지 못한다. 웹 사진은 공식 홈 사진과 따로 정한다
 * @param labelInImageEnabled 사진 속 호수 표기로 이은 색({@code LABEL_IN_IMAGE})을 쓸지. 기준 세트에서 판독 일치율이 95% 이상일
 *     때 켠다
 * @param sourceValueSites 사이트가 준 색값({@code SOURCE_VALUE})을 쓰는 사이트({@code products.source} 값 그대로).
 *     옵션과 색값의 연결을 확인한 사이트만 적는다
 * @param llmEstimateEnabled 모델 추정 색({@code LLM_ESTIMATE})을 쓸지. 기준 세트로 정확도를 확인한 뒤에만 켠다
 * @param layoutMatchMaxDeltaE 이름 없는 칸을 위치로 맞출 때 허용하는 기존 색과 새 색의 최대 ΔE2000
 */
@ConfigurationProperties(prefix = "catalog.color")
public record CatalogColorProperties(
    @DefaultValue Map<ColorSource, Double> minQuality,
    @DefaultValue("false") boolean labelInImageEnabled,
    @DefaultValue Set<String> sourceValueSites,
    @DefaultValue("false") boolean llmEstimateEnabled,
    @DefaultValue("5.0") double layoutMatchMaxDeltaE) {}
