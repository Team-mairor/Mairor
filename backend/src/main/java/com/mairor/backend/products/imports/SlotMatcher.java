package com.mairor.backend.products.imports;

import com.mairor.backend.products.entity.NameSource;
import com.mairor.backend.products.entity.ProductShadeColor;
import com.mairor.backend.products.imports.CollectedProduct.CollectedColor;
import com.mairor.backend.products.imports.CollectedProduct.SlotOrderBasis;
import com.mairor.backend.products.support.CatalogTextNormalizer;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * 재수집한 호수의 칸을 기존 칸과 맞춘다. **칸 수나 격자가 같다는 것은 같은 칸이라는 증거가 아니다**(9구 팔레트는 사진이 돌아가도 같은 격자). 대응을 확인할 수 있을
 * 때만 같은 {@code colorId}를 이어 쓰고, 확인할 수 없으면 기존 칸을 그대로 둔다.
 *
 * <p>근거는 둘이다.
 *
 * <ul>
 *   <li><b>이름·번호</b>: 기존 칸과 새 칸이 모두 사이트 글자나 사진 인쇄 이름({@code SITE_TEXT}·{@code IMAGE_PRINT})을 가지고, 한
 *       호수 안에서 이름이 겹치지 않고, 이름 집합이 같을 때. 순서대로 센 번호({@code NONE})는 근거가 아니다.
 *   <li><b>위치</b>: 기존 칸이 모두 HEX 를 가지고, 어느 쪽에도 이름 근거가 없고, 칸 수가 같고, 새 결과의 순서가 {@code GRID}이고, **모든**
 *       칸의 기존 색과 새 색의 ΔE2000 이 기준값 이하일 때. 하나라도 넘거나 새 칸에 색이 없어 비교할 수 없으면 믿지 않는다. 이름이 일부 칸에만 있는 경우는
 *       위치로 맞추지 않는다.
 * </ul>
 *
 * <p><b>단일 칸 예외</b>: 기존 칸과 새 칸이 각각 **하나뿐**이면 맞출 위치가 없어 헷갈릴 일이 없다. 두 칸이 서로 다른 이름 근거를 가진 경우가 아니면 같은
 * 칸으로 본다(같은 {@code colorId}). 호수는 이미 옵션 값으로 확인된 상태다. 그래서 단색 제품의 사진 색을 더 믿을 수 있는 공식 색값으로 바꾸는 일이 막히지
 * 않는다. 색을 바꿀지는 {@link ColorReplacementPolicy}가 출처·승인·최신성으로 따로 정한다.
 *
 * <p>기존 칸에 HEX 가 없으면 ΔE 를 계산할 수 없어 위치로 맞추지 않는다. HEX 가 있는 칸과 없는 칸이 섞여 있고 이름 근거가 없으면 호수 전체를 그대로 둔다.
 * 예외로, 기존 칸이 **전부** HEX 가 없고 칸을 가리키는 참조가 **하나도 없으면** 새 칸 구성으로 교체한다(같은 칸이라고 주장하지 않으므로 새 {@code
 * colorId}).
 */
public final class SlotMatcher {

  public enum Kind {
    /** 새 수집에 칸이 없다. 할 일이 없다. */
    NONE,
    /** 기존 칸이 없다. 새 칸을 모두 만든다. */
    CREATE,
    /** 기존 칸과 새 칸의 대응을 확인했다. */
    MATCHED,
    /** 기존 칸이 전부 HEX 가 없고 참조도 없어 새 칸 구성으로 바꾼다(기존 칸은 지운다). */
    REPLACE_ALL,
    /** 대응을 확인할 수 없어 기존 칸을 그대로 둔다. */
    KEPT
  }

  /**
   * 칸 하나의 짝. {@code existing}이 {@code null}이면 새 칸이다.
   *
   * @param sortOrder 반영 뒤의 칸 순서(새 수집의 순서)
   */
  public record Pair(ProductShadeColor existing, CollectedColor incoming, int sortOrder) {}

  /**
   * @param removed {@link Kind#REPLACE_ALL}일 때 지울 기존 칸
   * @param reasons {@link Kind#KEPT}이면 {@code SHADE_LAYOUT_CHANGED}
   */
  public record Pairing(
      Kind kind, List<Pair> pairs, List<ProductShadeColor> removed, Set<ImportReason> reasons) {}

  private SlotMatcher() {}

  /**
   * @param existing 호수의 기존 칸
   * @param incoming 새로 수집한 칸
   * @param basis 새 칸 순서를 어떻게 정했나
   * @param hasReferences 기존 칸을 가리키는 참조(영상 연결·저장된 매칭·실행·리포트)가 하나라도 있는가
   * @param maxDeltaE 위치로 맞출 때 허용하는 ΔE2000
   */
  public static Pairing match(
      List<ProductShadeColor> existing,
      List<CollectedColor> incoming,
      SlotOrderBasis basis,
      boolean hasReferences,
      double maxDeltaE) {
    if (incoming.isEmpty()) {
      return new Pairing(Kind.NONE, List.of(), List.of(), Set.of());
    }
    if (existing.isEmpty()) {
      return new Pairing(Kind.CREATE, freshPairs(incoming), List.of(), Set.of());
    }

    List<Pair> byName = byName(existing, incoming);
    if (byName != null) {
      return new Pairing(Kind.MATCHED, byName, List.of(), Set.of());
    }

    if (existing.size() == 1
        && incoming.size() == 1
        && !namesContradict(existing.get(0), incoming.get(0))) {
      CollectedColor color = incoming.get(0);
      return new Pairing(
          Kind.MATCHED,
          List.of(new Pair(existing.get(0), color, color.sortOrder())),
          List.of(),
          Set.of());
    }

    long withColor = existing.stream().filter(c -> c.getColor() != null).count();
    if (withColor == 0) {
      if (!hasReferences) {
        return new Pairing(Kind.REPLACE_ALL, freshPairs(incoming), List.copyOf(existing), Set.of());
      }
      return kept();
    }
    if (withColor == existing.size()) {
      List<Pair> byPosition = byPosition(existing, incoming, basis, maxDeltaE);
      if (byPosition != null) {
        return new Pairing(Kind.MATCHED, byPosition, List.of(), Set.of());
      }
    }
    return kept();
  }

  private static Pairing kept() {
    return new Pairing(Kind.KEPT, List.of(), List.of(), Set.of(ImportReason.SHADE_LAYOUT_CHANGED));
  }

  private static List<Pair> freshPairs(List<CollectedColor> incoming) {
    return incoming.stream().map(c -> new Pair(null, c, c.sortOrder())).toList();
  }

  /** 이름으로 맞춘다. 근거가 성립하지 않으면 {@code null}. */
  private static List<Pair> byName(
      List<ProductShadeColor> existing, List<CollectedColor> incoming) {
    if (existing.size() != incoming.size()) {
      return null;
    }
    Map<String, ProductShadeColor> existingByName = new HashMap<>();
    for (ProductShadeColor slot : existing) {
      if (!hasNameEvidence(slot.getNameSource()) || slot.getName() == null) {
        return null;
      }
      if (existingByName.put(CatalogTextNormalizer.normalize(slot.getName()), slot) != null) {
        return null;
      }
    }
    Set<String> seen = new HashSet<>();
    List<Pair> pairs = new ArrayList<>();
    for (CollectedColor color : incoming) {
      if (!hasNameEvidence(color.nameSource()) || color.name() == null) {
        return null;
      }
      String key = CatalogTextNormalizer.normalize(color.name());
      ProductShadeColor match = existingByName.get(key);
      if (match == null || !seen.add(key)) {
        return null;
      }
      pairs.add(new Pair(match, color, color.sortOrder()));
    }
    return pairs;
  }

  /** 위치로 맞춘다. 근거가 성립하지 않으면 {@code null}. */
  private static List<Pair> byPosition(
      List<ProductShadeColor> existing,
      List<CollectedColor> incoming,
      SlotOrderBasis basis,
      double maxDeltaE) {
    if (basis != SlotOrderBasis.GRID || existing.size() != incoming.size()) {
      return null;
    }
    boolean anyName =
        existing.stream().anyMatch(c -> hasNameEvidence(c.getNameSource()))
            || incoming.stream().anyMatch(c -> hasNameEvidence(c.nameSource()));
    if (anyName) {
      return null;
    }
    List<ProductShadeColor> oldSlots =
        existing.stream().sorted(Comparator.comparingInt(ProductShadeColor::getSortOrder)).toList();
    List<CollectedColor> newSlots =
        incoming.stream().sorted(Comparator.comparingInt(CollectedColor::sortOrder)).toList();
    List<Pair> pairs = new ArrayList<>();
    for (int i = 0; i < oldSlots.size(); i++) {
      CollectedColor color = newSlots.get(i);
      if (!color.hasColor()
          || ColorDifference.deltaE2000(oldSlots.get(i).getColor().getHex(), color.hex())
              > maxDeltaE) {
        return null;
      }
      pairs.add(new Pair(oldSlots.get(i), color, color.sortOrder()));
    }
    return pairs;
  }

  /** 두 칸이 모두 이름 근거를 가지는데 이름이 다르면 서로 다른 칸이라는 증거다. */
  private static boolean namesContradict(ProductShadeColor old, CollectedColor incoming) {
    if (!hasNameEvidence(old.getNameSource()) || !hasNameEvidence(incoming.nameSource())) {
      return false;
    }
    if (old.getName() == null || incoming.name() == null) {
      return false;
    }
    return !CatalogTextNormalizer.normalize(old.getName())
        .equals(CatalogTextNormalizer.normalize(incoming.name()));
  }

  private static boolean hasNameEvidence(NameSource source) {
    return source == NameSource.SITE_TEXT || source == NameSource.IMAGE_PRINT;
  }
}
