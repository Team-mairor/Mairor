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

  @Test
  void aLinkedItemKeepsTheMembersColorForASingleSlotShade() {
    UUID shadeId = UUID.randomUUID();
    PouchItem item = linked(shadeId, PouchColor.userInput("#123456"));
    ProductShade shade = shadeWith(slot("#AA0000"));

    var candidate = assembler.assemble(item, Map.of(shadeId, shade));

    assertThat(candidate.colors())
        .containsExactly(new RecommendationCandidateSelector.ColorOption(null, "#123456"));
  }

  @Test
  void aLinkedPaletteUsesCatalogSlotsInsteadOfTheMembersColor() {
    UUID shadeId = UUID.randomUUID();
    PouchItem item = linked(shadeId, PouchColor.userInput("#123456"));
    ProductShadeColor first = slot("#AA0000");
    ProductShadeColor second = slot("#00AA00");
    ProductShade shade = shadeWith(first, second);

    var candidate = assembler.assemble(item, Map.of(shadeId, shade));

    assertThat(candidate.colors())
        .extracting(RecommendationCandidateSelector.ColorOption::hex)
        .containsExactly("#AA0000", "#00AA00");
  }

  private static PouchItem linked(UUID shadeId, PouchColor color) {
    PouchItem item =
        new PouchItem(
            UUID.randomUUID(),
            RegistrationMode.CATALOG,
            UUID.randomUUID(),
            shadeId,
            "LIP",
            "LIP_TINT",
            "브랜드",
            "제품",
            "01",
            color);
    ReflectionTestUtils.setField(item, "id", UUID.randomUUID());
    return item;
  }

  private static ProductShade shadeWith(ProductShadeColor... slots) {
    ProductShade shade = mock(ProductShade.class);
    when(shade.getColors()).thenReturn(List.of(slots));
    return shade;
  }

  private static ProductShadeColor slot(String hex) {
    ProductShadeColor slot = mock(ProductShadeColor.class);
    when(slot.hasUsableColor()).thenReturn(true);
    when(slot.getId()).thenReturn(UUID.randomUUID());
    com.mairor.backend.products.entity.ShadeColor color =
        mock(com.mairor.backend.products.entity.ShadeColor.class);
    when(color.getHex()).thenReturn(hex);
    when(slot.getColor()).thenReturn(color);
    return slot;
  }
}
