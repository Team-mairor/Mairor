package com.mairor.backend.pouch.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyCollection;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.mairor.backend.pouch.dto.PouchItemResponse;
import com.mairor.backend.pouch.entity.PouchColor;
import com.mairor.backend.pouch.entity.PouchItem;
import com.mairor.backend.pouch.entity.RegistrationMode;
import com.mairor.backend.products.entity.ColorSource;
import com.mairor.backend.products.entity.NameSource;
import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.entity.ProductCategory;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductType;
import com.mairor.backend.products.entity.ReviewStatus;
import com.mairor.backend.products.repository.ProductShadeRepository;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

class PouchResponseAssemblerTest {

  private final ProductShadeRepository shades = mock(ProductShadeRepository.class);
  private final PouchResponseAssembler assembler = new PouchResponseAssembler(shades);

  @Test
  void paletteItemWithoutStoredColorShowsTheFirstUsableSlotAsPreview() {
    ProductShade palette = shade(1);
    slot(palette, 1, "#E8CAC0", ReviewStatus.BELOW_THRESHOLD);
    slot(palette, 2, "#EAD1CB", ReviewStatus.AUTO_APPROVED);
    slot(palette, 3, "#111111", ReviewStatus.AUTO_APPROVED);
    when(shades.findByIdIn(anyCollection())).thenReturn(List.of(palette));

    PouchItemResponse response = assembler.assemble(catalogItem(palette, null));

    assertThat(response.color().hex()).isEqualTo("#EAD1CB");
    assertThat(response.color().source()).isEqualTo("CATALOG");
    assertThat(response.colorSource()).isEqualTo("CATALOG");
  }

  @Test
  void storedColorIsNotReplacedByThePreview() {
    ProductShade single = shade(1);
    slot(single, 1, "#8A817B", ReviewStatus.AUTO_APPROVED);
    PouchItem item = catalogItem(single, PouchColor.catalog("#112233", false));

    PouchItemResponse response = assembler.assemble(item);

    assertThat(response.color().hex()).isEqualTo("#112233");
    verifyNoInteractions(shades);
  }

  @Test
  void paletteWithoutUsableSlotAndManualItemsStayWithoutColor() {
    ProductShade hidden = shade(1);
    slot(hidden, 1, "#E8CAC0", ReviewStatus.REJECTED);
    when(shades.findByIdIn(anyCollection())).thenReturn(List.of(hidden));
    PouchItem manual =
        new PouchItem(
            UUID.randomUUID(),
            RegistrationMode.MANUAL,
            null,
            null,
            "LIP",
            "LIPSTICK",
            "Brand",
            "Manual",
            null,
            null);

    List<PouchItemResponse> responses =
        assembler.assembleAll(List.of(catalogItem(hidden, null), manual));

    assertThat(responses).extracting(PouchItemResponse::color).containsOnlyNulls();
    assertThat(responses).extracting(PouchItemResponse::colorSource).containsOnly("NONE");
  }

  private static ProductShade shade(int order) {
    ProductCategory category = new ProductCategory("CHEEK", "치크", true, true, 4);
    ProductType type = new ProductType("BLUSHER", category, "블러셔", 1);
    ProductShade shade = new Product(type, "브랜드", "제품").addShade("아몬드 바닐라", order, null);
    ReflectionTestUtils.setField(shade, "id", UUID.randomUUID());
    return shade;
  }

  private static void slot(ProductShade shade, int order, String hex, ReviewStatus status) {
    shade
        .addColor(order, null, NameSource.NONE)
        .assignColor(ColorSource.SAMPLE, hex, false, status, null);
  }

  private static PouchItem catalogItem(ProductShade shade, PouchColor color) {
    return new PouchItem(
        UUID.randomUUID(),
        RegistrationMode.CATALOG,
        UUID.randomUUID(),
        shade.getId(),
        "CHEEK",
        "BLUSHER",
        "브랜드",
        "제품",
        shade.getName(),
        color);
  }
}
