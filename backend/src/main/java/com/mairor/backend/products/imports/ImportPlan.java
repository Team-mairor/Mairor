package com.mairor.backend.products.imports;

import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductShadeColor;
import com.mairor.backend.products.imports.CollectedProduct.CollectedColor;
import com.mairor.backend.products.imports.CollectedProduct.CollectedShade;
import java.util.List;
import java.util.Set;

/**
 * 수집 상품 한 건을 DB 에 어떻게 반영할지 정한 계획. 계획만 세우고 DB 는 바꾸지 않는다. 계획을 실행하는 것(저장, 파우치·가이드 버전 올리기, 실행 기록)은 적재
 * 단계(S15P31A306-295)가 하고, 판정만 보는 시험 실행(dry-run)은 이 계획을 그대로 결과로 돌려준다.
 *
 * @param outcome 제품 단위 판정
 * @param item 읽은 수집 상품
 * @param type 확정한 카테고리·종류. {@link Outcome#UNCLASSIFIED}이면 {@code null}
 * @param existing 이미 있는 제품. {@link Outcome#NEW}·{@link Outcome#UNCLASSIFIED}이면 {@code null}. {@link
 *     Outcome#AMBIGUOUS}이면 같은 (종류, 브랜드, 제품명)을 이미 가진 다른 제품(출처가 다르거나, 갱신하려는 이름이 겹쳐 {@code
 *     PRODUCT_NAME_CONFLICT}인 경우)
 * @param cleanedName 판매 배지를 지운 상품명(저장할 이름)
 * @param shades 호수별 계획. {@link Outcome#NEW}·{@link Outcome#UPDATE}일 때만 채운다
 * @param reasons 건 전체의 사유
 * @param downgrades 호수 계획이 다루지 않은 기존 호수의 칸 중 사용 불가로 내릴 칸. 갱신 중인 제품의 기존 호수·칸 전체를 호수 대응과 독립적으로 검사한
 *     결과다. 이번 수집에서 빠진 호수, 모호해서 보류한 호수, 계획에 들어가지 않은 호수의 칸이 대상이다. 호수 계획이 다룬 칸은 각 {@code SlotPlan}이
 *     처리한다
 */
public record ImportPlan(
    Outcome outcome,
    CollectedProduct item,
    TypeResolution type,
    Product existing,
    String cleanedName,
    List<ShadePlan> shades,
    Set<ImportReason> reasons,
    List<ProductShadeColor> downgrades) {

  /** 제품 단위 판정. */
  public enum Outcome {
    /** 새 제품이다. */
    NEW,
    /** 같은 출처·상품 번호의 기존 제품을 갱신한다. */
    UPDATE,
    /** 기존 제품이 더 최근에 수집됐다. 반영하지 않는다. */
    STALE,
    /** 다른 출처에서 온 같은 (종류, 브랜드, 제품명) 제품이 있다. 자동으로 합치지 않는다. */
    AMBIGUOUS,
    /** 카테고리·종류를 정할 수 없다. */
    UNCLASSIFIED
  }

  /** 일부만 반영했거나 기존 값을 지킨 사유가 있는가. */
  public boolean isPartial() {
    return allReasons().stream().anyMatch(ImportReason::isPartial);
  }

  /** 건 전체와 호수·칸의 모든 사유. */
  public Set<ImportReason> allReasons() {
    java.util.Set<ImportReason> all = new java.util.LinkedHashSet<>(reasons);
    for (ShadePlan shade : shades) {
      all.addAll(shade.reasons());
    }
    return Set.copyOf(all);
  }

  /**
   * 호수 하나의 계획.
   *
   * @param action 만들기, 갱신, 보류
   * @param existing 갱신할 기존 호수. 만들기·보류면 {@code null}(보류는 모호한 기존 호수를 알 수 없다)
   * @param shade 대표 옵션. 이름·순서·칸의 기준이다
   * @param renameTo 갱신할 때 호수 이름을 바꿔야 하면 새 이름(앞뒤 공백을 지운 원문). 바꿀 필요가 없거나 다른 호수와 이름이 겹쳐 바꿀 수 없으면
   *     {@code null}
   * @param newPrimaryOptionId 호수의 대표 옵션 값. 만들 때는 대표 옵션의 값, 갱신할 때는 대표를 바꿔야 할 때만 새 값(아니면 {@code
   *     null})
   * @param addAliases 별칭에 더할 옵션 값
   * @param removeAliases 대표가 되어 별칭에서 뺄 옵션 값
   * @param slots 칸 계획. 보류면 {@code null}
   * @param reasons 이 호수의 사유
   */
  public record ShadePlan(
      Action action,
      ProductShade existing,
      CollectedShade shade,
      String renameTo,
      String newPrimaryOptionId,
      List<String> addAliases,
      List<String> removeAliases,
      SlotPlan slots,
      Set<ImportReason> reasons) {

    public enum Action {
      CREATE,
      UPDATE,
      /** 이 호수는 반영하지 않는다(사유는 {@code reasons}). */
      HELD
    }
  }

  /**
   * 호수의 칸 계획.
   *
   * @param kind 칸을 맞춘 방식
   * @param steps 칸마다의 처리. {@link SlotMatcher.Kind#KEPT}·{@link SlotMatcher.Kind#NONE}이면 비어 있다
   * @param removed {@link SlotMatcher.Kind#REPLACE_ALL}일 때 지울 기존 칸
   * @param downgrades 칸 대응과 상관없이 사용 불가로 내릴 기존 칸. 쓰던 색의 출처가 현재 정책에서 쓸 수 없는 출처가 됐는데 이번 수집에서 짝을 찾지 못한
   *     칸이다({@code steps}에 있는 칸은 거기서 처리한다). 새 칸이 없거나({@code NONE}) 대응을 확인하지 못해({@code KEPT}) 칸 배치를
   *     그대로 두더라도 금지된 출처의 색은 중단한다. 값은 남기고 승인 상태만 {@code BELOW_THRESHOLD}로 바꾼다
   */
  public record SlotPlan(
      SlotMatcher.Kind kind,
      List<SlotStep> steps,
      List<ProductShadeColor> removed,
      List<ProductShadeColor> downgrades) {}

  /**
   * 칸 하나의 처리.
   *
   * @param existing 기존 칸. 새 칸이면 {@code null}
   * @param incoming 새 수집 칸
   * @param sortOrder 반영 뒤 칸 순서
   * @param color 색 처리. 새 칸에 색이 없고 기존 칸도 없으면 {@code ADOPT} 없이 {@code KEPT_NOT_FOUND}가 나온다
   */
  public record SlotStep(
      ProductShadeColor existing,
      CollectedColor incoming,
      int sortOrder,
      ColorReplacementPolicy.Result color) {}
}
