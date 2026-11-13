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

  /**
   * 회원이 넣은 색(USER_INPUT)이 있으면 그 색을 쓴다. 다만 카탈로그 팔레트(칸 2개 이상) 호수에 연결된 항목은 회원 색 하나를 특정 칸에 붙일 수 없어 카탈로그
   * 칸 색을 쓴다(수집 요청 자동 연결, S15P31A306-517).
   */
  public RecommendationCandidateSelector.Candidate assemble(
      PouchItem item, Map<UUID, ProductShade> shadesById) {
    List<RecommendationCandidateSelector.ColorOption> colors = new ArrayList<>();
    PouchColor storedColor = item.getColor();
    ProductShade shade =
        item.getRegistrationMode() == RegistrationMode.CATALOG && item.getShadeId() != null
            ? shadesById.get(item.getShadeId())
            : null;
    boolean palette = shade != null && shade.getColors().size() >= 2;

    if (storedColor != null
        && storedColor.getSource() == PouchColor.Source.USER_INPUT
        && !palette) {
      colors.add(new RecommendationCandidateSelector.ColorOption(null, storedColor.getHex()));
    } else if (shade != null) {
      for (ProductShadeColor slot : shade.getColors()) {
        if (slot.hasUsableColor()) {
          colors.add(
              new RecommendationCandidateSelector.ColorOption(
                  slot.getId(), slot.getColor().getHex()));
        }
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
