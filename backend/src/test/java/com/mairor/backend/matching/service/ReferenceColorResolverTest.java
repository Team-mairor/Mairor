package com.mairor.backend.matching.service;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import tools.jackson.databind.node.JsonNodeFactory;

class ReferenceColorResolverTest {

  private final ReferenceColorResolver resolver = new ReferenceColorResolver();

  @Test
  void readsOnlyExplicitHexAndNormalizesItsCase() {
    var targetColor = JsonNodeFactory.instance.objectNode().put("hex", "#aBc123");

    var color = resolver.resolve(null, targetColor);

    assertThat(color)
        .isEqualTo(new ReferenceColorResolver.ReferenceColor("#ABC123", "VIDEO_ESTIMATE", true));
  }

  @Test
  void doesNotInferHexFromDescriptionOrInvalidColor() {
    var textColor = JsonNodeFactory.instance.objectNode().put("value", "진한 브라운");
    var invalidHex = JsonNodeFactory.instance.objectNode().put("hex", "진한 브라운");

    assertThat(resolver.resolve(null, textColor)).isNull();
    assertThat(resolver.resolve(null, invalidHex)).isNull();
    assertThat(resolver.resolve(null, null)).isNull();
  }
}
