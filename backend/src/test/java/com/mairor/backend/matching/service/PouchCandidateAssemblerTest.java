package com.mairor.backend.matching.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.mairor.backend.pouch.entity.PouchColor;
import com.mairor.backend.pouch.entity.PouchItem;
import com.mairor.backend.pouch.entity.RegistrationMode;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductShadeColor;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

class PouchCandidateAssemblerTest {

  private final PouchCandidateAssembler assembler = new PouchCandidateAssembler();

  @Test
  void ignoresStoredCatalogCopyWhenCurrentCatalogHasNoUsableColor() {
    UUID productId = UUID.randomUUID();
    UUID shadeId = UUID.randomUUID();
    PouchItem item =
        new PouchItem(
            UUID.randomUUID(),
            RegistrationMode.CATALOG,
            productId,
            shadeId,
            "LIP",
            "LIP_TINT",
            "브랜드",
            "제품",
            "01",
            PouchColor.catalog("#112233", true));
    ReflectionTestUtils.setField(item, "id", UUID.randomUUID());
    ProductShade shade = mock(ProductShade.class);
    ProductShadeColor unusableColor = mock(ProductShadeColor.class);
    when(shade.getColors()).thenReturn(List.of(unusableColor));
    when(unusableColor.hasUsableColor()).thenReturn(false);

    var candidate = assembler.assemble(item, Map.of(shadeId, shade));

    assertThat(candidate.colors()).isEmpty();
  }

  @Test
  void manualColorIsUsedWithoutCatalogSlotId() {
    PouchItem item =
        new PouchItem(
            UUID.randomUUID(),
            RegistrationMode.MANUAL,
            null,
            null,
            "LIP",
            "LIP_TINT",
            "브랜드",
            "제품",
            "01",
            PouchColor.userInput("#123456"));
    ReflectionTestUtils.setField(item, "id", UUID.randomUUID());

    var candidate = assembler.assemble(item, Map.of());

    assertThat(candidate.colors())
        .containsExactly(new RecommendationCandidateSelector.ColorOption(null, "#123456"));
  }
}
