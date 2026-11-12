package com.mairor.backend.products.imports;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.products.entity.ColorSource;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.core.env.Environment;

/**
 * 운영 설정 파일({@code application-prod.yml})의 색 품질 기준값이 {@link CatalogColorProperties}로 실제로 읽히는지 확인한다.
 *
 * <p>출처 이름({@code PRODUCT_PHOTO})이 맵 키라 환경변수 이름으로 덮으면 키가 바뀐다. 그래서 운영 파일에 기본값을 두고 값마다 따로 둔 환경변수로만
 * 바꾼다. 앱 전체를 띄우지 않고 설정 파일만 읽는다.
 */
class CatalogColorProdConfigTest {

  private final ApplicationContextRunner runner =
      new ApplicationContextRunner()
          .withInitializer(new ConfigDataApplicationContextInitializer())
          .withPropertyValues("spring.config.import=optional:classpath:/does-not-exist.properties");

  private static CatalogColorProperties bind(Environment environment) {
    return Binder.get(environment).bindOrCreate("catalog.color", CatalogColorProperties.class);
  }

  @Test
  void prodProfileUsesTheThresholdsChosenWithTheReviewSheet() {
    runner
        .withPropertyValues("spring.profiles.active=prod")
        .run(
            context -> {
              CatalogColorProperties properties = bind(context.getEnvironment());

              assertThat(properties.minQuality())
                  .isEqualTo(
                      Map.of(ColorSource.PRODUCT_PHOTO, 0.75, ColorSource.SWATCH_CHIP, 0.55));
              assertThat(properties.labelInImageEnabled()).isTrue();
              assertThat(properties.llmEstimateEnabled()).isFalse();
            });
  }

  @Test
  void eachThresholdCanBeChangedWithItsOwnEnvironmentVariable() {
    runner
        .withPropertyValues(
            "spring.profiles.active=prod",
            "CATALOG_COLOR_MIN_QUALITY_PRODUCT_PHOTO=0.8",
            "CATALOG_COLOR_LABEL_IN_IMAGE_ENABLED=false")
        .run(
            context -> {
              CatalogColorProperties properties = bind(context.getEnvironment());

              assertThat(properties.minQuality().get(ColorSource.PRODUCT_PHOTO)).isEqualTo(0.8);
              assertThat(properties.minQuality().get(ColorSource.SWATCH_CHIP)).isEqualTo(0.55);
              assertThat(properties.labelInImageEnabled()).isFalse();
            });
  }

  @Test
  void otherProfilesKeepPassingNoPhotoColors() {
    runner
        .withPropertyValues("spring.profiles.active=dev")
        .run(
            context -> {
              CatalogColorProperties properties = bind(context.getEnvironment());

              assertThat(properties.minQuality()).isEmpty();
              assertThat(properties.labelInImageEnabled()).isFalse();
            });
  }
}
