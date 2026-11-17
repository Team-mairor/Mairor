package com.mairor.backend.guides.service;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

class GuideStepMakeupTest {

  private final ObjectMapper mapper = new ObjectMapper();

  @Test
  void lensStepIsReadAsLensEvenWhenAnalysisLabeledItFoundation() throws Exception {
    JsonNode step =
        mapper.readTree(
            "{\"makeup\":\"foundation\",\"partLabel\":\"렌즈 끼기\","
                + "\"product\":{\"brand\":\"Gemhour\",\"name\":\"에브리데이 에센셜\"}}");

    assertThat(GuideStepMakeup.of(step)).isEqualTo(GuideStepMakeup.LENS);
  }

  @Test
  void productNameWithLensAlsoCountsAsLens() throws Exception {
    JsonNode step =
        mapper.readTree(
            "{\"makeup\":\"eyeliner\",\"partLabel\":\"눈에 포인트\","
                + "\"product\":{\"name\":\"데일리 컬러렌즈\"}}");

    assertThat(GuideStepMakeup.of(step)).isEqualTo("lens");
  }

  @Test
  void otherStepsKeepTheirMakeupAndMissingMakeupIsEmpty() throws Exception {
    assertThat(
            GuideStepMakeup.of(
                mapper.readTree(
                    "{\"makeup\":\"foundation\",\"partLabel\":\"쿠션으로 피부 표현\","
                        + "\"product\":{\"name\":\"글로우 쿠션\"}}")))
        .isEqualTo("foundation");
    assertThat(GuideStepMakeup.of(mapper.readTree("{\"partLabel\":\"입술\"}"))).isEmpty();
  }
}
