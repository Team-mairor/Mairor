package com.mairor.backend.pouch.service;

import com.mairor.backend.pouch.dto.PouchItemResponse;
import com.mairor.backend.pouch.dto.PouchItemResponse.ColorInfo;
import com.mairor.backend.pouch.entity.PouchItem;
import com.mairor.backend.pouch.entity.RegistrationMode;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductShadeColor;
import com.mairor.backend.products.repository.ProductShadeRepository;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.stereotype.Component;

/**
 * 파우치 항목을 응답으로 바꾼다. 카탈로그 팔레트 항목은 저장한 색이 없어서, 화면에 색을 보여 주도록 호수의 첫 번째 쓸 수 있는 칸 색을 표시용으로 얹는다. 이 색은
 * 응답에만 쓰고 저장하거나 추천 계산에 쓰지 않는다. 호출자의 트랜잭션 안에서 호출한다.
 */
@Component
public class PouchResponseAssembler {

  private final ProductShadeRepository shades;

  public PouchResponseAssembler(ProductShadeRepository shades) {
    this.shades = shades;
  }

  public PouchItemResponse assemble(PouchItem item) {
    return assembleAll(List.of(item)).getFirst();
  }

  public List<PouchItemResponse> assembleAll(Collection<PouchItem> items) {
    List<UUID> shadeIds =
        items.stream()
            .filter(PouchResponseAssembler::needsPreview)
            .map(PouchItem::getShadeId)
            .distinct()
            .toList();
    Map<UUID, ProductShade> shadesById =
        shadeIds.isEmpty()
            ? Map.of()
            : shades.findByIdIn(shadeIds).stream()
                .collect(Collectors.toMap(ProductShade::getId, Function.identity()));
    return items.stream()
        .map(
            item ->
                PouchItemResponse.from(
                    item,
                    needsPreview(item) ? previewColor(shadesById.get(item.getShadeId())) : null))
        .toList();
  }

  private static boolean needsPreview(PouchItem item) {
    return item.getColor() == null
        && item.getRegistrationMode() == RegistrationMode.CATALOG
        && item.getShadeId() != null;
  }

  private static ColorInfo previewColor(ProductShade shade) {
    if (shade == null) {
      return null;
    }
    for (ProductShadeColor slot : shade.getColors()) {
      if (slot.hasUsableColor()) {
        return new ColorInfo(
            "sRGB", slot.getColor().getHex(), "CATALOG", slot.getColor().isEstimated());
      }
    }
    return null;
  }
}
