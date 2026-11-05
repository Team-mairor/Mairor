package com.mairor.backend.products.imports;

import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.imports.CollectedProduct.CollectedShade;
import com.mairor.backend.products.imports.CollectedProduct.VariantHints;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * 호수를 묶고, 기존 호수와 맞춘다.
 *
 * <p><b>묶기</b>: 한 상품 안에서 호수명의 비교 키({@link CatalogNameCleaner#shadeComparisonKey})가 같은 옵션들은 **충돌 신호가
 * 없을 때만** 한 호수로 합친다. 모든 옵션이 구분 정보({@code variantHints})를 보냈고 그 값(용량·구성·제형·옵션 속성·정가)이 모두 같아야 한다. 구분
 * 정보를 보내지 않았으면 '충돌 없음'이 아니라 '모름'이라 합치지 않는다. 합치지 않은 옵션은 따로 둔다. 합칠 때 대표 옵션은 지울 문구가 없던 옵션(없으면 먼저 온
 * 옵션)이고, 나머지 옵션 값은 별칭이 된다.
 *
 * <p><b>기존 호수와 맞추기</b>: 옵션 값(또는 별칭)이 일치하는 기존 호수가 있으면 같은 호수다. 일치가 없는데 같은 이름(비교 키)의 기존 호수가 있으면 같은
 * 호수인지 알 수 없어 보류한다 (시드나 직접 넣은 호수는 옵션 값이 없다). 둘 다 없으면 새 호수다. 출처에서 사라진 기존 호수는 그대로 둔다(파우치가 참조한다).
 */
public final class ShadeMatcher {

  /**
   * 한 호수가 될 옵션들.
   *
   * @param representative 호수의 이름·칸을 정하는 대표 옵션
   * @param optionIds 이 호수의 모든 옵션 값(대표 먼저)
   * @param mergeHeld 비교 키가 같은 다른 옵션이 있지만 충돌 신호나 구분 정보 부재로 합치지 않았다
   */
  public record Group(CollectedShade representative, List<String> optionIds, boolean mergeHeld) {}

  /** 기존 호수와 맞춘 결과. */
  public sealed interface Match permits Create, Update, Ambiguous {}

  /** 기존 호수가 없다. */
  public record Create() implements Match {}

  /**
   * 같은 호수다.
   *
   * @param newPrimaryOptionId 대표 옵션 값을 바꿔야 하면 새 값, 아니면 {@code null}(옛 대표가 사이트에서 사라지고 별칭으로 일치한 경우)
   * @param addAliases 별칭에 더할 옵션 값
   * @param removeAliases 대표가 되어 별칭에서 뺄 옵션 값
   */
  public record Update(
      ProductShade existing,
      String newPrimaryOptionId,
      List<String> addAliases,
      List<String> removeAliases)
      implements Match {}

  /** 같은 호수인지 알 수 없다. 이 호수는 반영하지 않는다. */
  public record Ambiguous() implements Match {}

  private ShadeMatcher() {}

  public static List<Group> group(List<CollectedShade> incoming) {
    Map<String, List<CollectedShade>> byKey = new LinkedHashMap<>();
    for (CollectedShade shade : incoming) {
      byKey
          .computeIfAbsent(
              CatalogNameCleaner.shadeComparisonKey(shade.name()), k -> new ArrayList<>())
          .add(shade);
    }
    List<Group> groups = new ArrayList<>();
    for (List<CollectedShade> options : byKey.values()) {
      if (options.size() == 1) {
        groups.add(new Group(options.get(0), List.of(options.get(0).sourceOptionId()), false));
      } else if (canMerge(options)) {
        CollectedShade representative = representative(options);
        List<String> ids = new ArrayList<>();
        ids.add(representative.sourceOptionId());
        options.stream()
            .map(CollectedShade::sourceOptionId)
            .filter(id -> !id.equals(representative.sourceOptionId()))
            .forEach(ids::add);
        groups.add(new Group(representative, List.copyOf(ids), false));
      } else {
        options.forEach(o -> groups.add(new Group(o, List.of(o.sourceOptionId()), true)));
      }
    }
    return groups;
  }

  public static Match find(Group group, List<ProductShade> existingShades) {
    Set<String> ids = new LinkedHashSet<>(group.optionIds());
    List<ProductShade> hits =
        existingShades.stream().filter(s -> carriesAnyOption(s, ids)).toList();
    if (hits.size() > 1) {
      return new Ambiguous();
    }
    if (hits.size() == 1) {
      return update(hits.get(0), group);
    }
    String key = CatalogNameCleaner.shadeComparisonKey(group.representative().name());
    boolean sameName =
        existingShades.stream()
            .anyMatch(s -> CatalogNameCleaner.shadeComparisonKey(s.getName()).equals(key));
    return sameName ? new Ambiguous() : new Create();
  }

  private static Match update(ProductShade existing, Group group) {
    String primary = existing.getSourceOptionId();
    Set<String> ids = new LinkedHashSet<>(group.optionIds());
    List<String> add = new ArrayList<>();
    List<String> remove = new ArrayList<>();
    String newPrimary = null;
    if (primary == null || !ids.contains(primary)) {
      // 옛 대표 옵션이 사라졌거나 처음부터 없었다. 별칭으로 일치했으므로 이번 대표 옵션이 새 대표가 된다
      newPrimary = group.representative().sourceOptionId();
      if (primary != null) {
        add.add(primary);
      }
      if (existing.getOptionAliases().contains(newPrimary)) {
        remove.add(newPrimary);
      }
    }
    String effectivePrimary = newPrimary != null ? newPrimary : primary;
    for (String id : ids) {
      if (!id.equals(effectivePrimary)
          && !existing.getOptionAliases().contains(id)
          && !add.contains(id)) {
        add.add(id);
      }
    }
    return new Update(existing, newPrimary, List.copyOf(add), List.copyOf(remove));
  }

  private static boolean carriesAnyOption(ProductShade shade, Set<String> ids) {
    if (shade.getSourceOptionId() != null && ids.contains(shade.getSourceOptionId())) {
      return true;
    }
    return shade.getOptionAliases().stream().anyMatch(ids::contains);
  }

  /** 구분 정보가 모두 있고 모두 같아야 합친다. */
  private static boolean canMerge(List<CollectedShade> options) {
    VariantHints first = options.get(0).variantHints();
    if (first == null) {
      return false;
    }
    return options.stream().allMatch(o -> Objects.equals(o.variantHints(), first));
  }

  private static CollectedShade representative(List<CollectedShade> options) {
    return options.stream()
        .filter(o -> !CatalogNameCleaner.hasRemovablePhrase(o.name()))
        .findFirst()
        .orElse(options.get(0));
  }
}
