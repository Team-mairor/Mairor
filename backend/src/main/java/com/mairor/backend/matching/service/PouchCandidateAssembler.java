package com.mairor.backend.matching.service;

import com.mairor.backend.pouch.entity.PouchColor;
import com.mairor.backend.pouch.entity.PouchItem;
import com.mairor.backend.pouch.entity.RegistrationMode;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductShadeColor;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Component;

/** 개인 저장값과 카탈로그 색 칸을 추천 계산용 후보로 변환한다. */
@Component
public final class PouchCandidateAssembler {

  public RecommendationCandidateSelector.Candidate assemble(
      PouchItem item, Map<UUID, ProductShade> shadesById) {
    List<RecommendationCandidateSelector.ColorOption> colors = new ArrayList<>();
    PouchColor storedColor = item.getColor();

    if (storedColor != null && storedColor.getSource() == PouchColor.Source.USER_INPUT) {
      colors.add(new RecommendationCandidateSelector.ColorOption(null, storedColor.getHex()));
    } else if (item.getRegistrationMode() == RegistrationMode.CATALOG) {
      if (item.getShadeId() != null) {
        ProductShade shade = shadesById.get(item.getShadeId());
        if (shade != null) {
          for (ProductShadeColor slot : shade.getColors()) {
            if (slot.hasUsableColor()) {
              colors.add(
                  new RecommendationCandidateSelector.ColorOption(
                      slot.getId(), slot.getColor().getHex()));
            }
          }
        }
      }
      if (colors.isEmpty() && storedColor != null) {
        colors.add(new RecommendationCandidateSelector.ColorOption(null, storedColor.getHex()));
      }
    }

    return new RecommendationCandidateSelector.Candidate(
        item.getId(),
        item.getProductId(),
        item.getShadeId(),
        item.getCategory(),
        item.getType(),
        colors);
  }
}
