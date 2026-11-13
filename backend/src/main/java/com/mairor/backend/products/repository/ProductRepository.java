package com.mairor.backend.products.repository;

import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.support.CatalogTextNormalizer;
import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository extends JpaRepository<Product, UUID> {

  /**
   * 종류·브랜드·제품명이 정확히 일치하는 제품을 찾는다. 브랜드·제품명은 {@link CatalogTextNormalizer}로 정규화해 비교하므로 대소문자·공백 차이는
   * 무시된다. {@code uk_products_type_brand_name} 인덱스를 그대로 쓴다.
   *
   * @throws IllegalArgumentException 브랜드나 제품명이 비었으면 (호출 전에 입력 검증을 한다)
   */
  default Optional<Product> findExact(String typeCode, String brand, String name) {
    return findByTypeCodeAndBrandNormalizedAndNameNormalized(
        typeCode, CatalogTextNormalizer.normalize(brand), CatalogTextNormalizer.normalize(name));
  }

  /** 여러 허용 종류에서 정규화된 브랜드·제품명이 정확히 일치하는 후보를 한 번에 읽는다. */
  default List<Product> findExact(Collection<String> typeCodes, String brand, String name) {
    if (typeCodes.isEmpty()) {
      return List.of();
    }
    return findAllByTypeCodeInAndBrandNormalizedAndNameNormalized(
        typeCodes, CatalogTextNormalizer.normalize(brand), CatalogTextNormalizer.normalize(name));
  }

  /** 수집 출처의 상품 번호로 찾는다. 같은 출처의 같은 번호는 한 제품이다({@code uk_products_source_product}). */
  @EntityGraph(attributePaths = {"category", "type"})
  Optional<Product> findBySourceAndSourceProductId(String source, String sourceProductId);

  /** 정규화된 값으로 찾는다. 정규화 전 값으로는 {@link #findExact}를 쓴다. */
  @EntityGraph(attributePaths = {"category", "type"})
  Optional<Product> findByTypeCodeAndBrandNormalizedAndNameNormalized(
      String typeCode, String brandNormalized, String nameNormalized);

  @EntityGraph(attributePaths = {"category", "type"})
  List<Product> findAllByTypeCodeInAndBrandNormalizedAndNameNormalized(
      Collection<String> typeCodes, String brandNormalized, String nameNormalized);

  /** 제품명 공백을 무시한 후보를 모두 찾는다. 다중 결과는 호출부에서 모호한 검색으로 처리한다. */
  @EntityGraph(attributePaths = {"category", "type"})
  List<Product> findAllByTypeCodeAndBrandNormalizedAndNameCompact(
      String typeCode, String brandNormalized, String nameCompact);

  default List<Product> findCompact(String typeCode, String brand, String name) {
    return findAllByTypeCodeAndBrandNormalizedAndNameCompact(
        typeCode, CatalogTextNormalizer.normalize(brand), CatalogTextNormalizer.compact(name));
  }

  /** 여러 허용 종류에서 공백 제거 제품명이 일치하는 후보를 한 번에 읽는다. */
  default List<Product> findCompact(Collection<String> typeCodes, String brand, String name) {
    if (typeCodes.isEmpty()) {
      return List.of();
    }
    return findAllByTypeCodeInAndBrandNormalizedAndNameCompact(
        typeCodes, CatalogTextNormalizer.normalize(brand), CatalogTextNormalizer.compact(name));
  }

  @EntityGraph(attributePaths = {"category", "type"})
  List<Product> findAllByTypeCodeInAndBrandNormalizedAndNameCompact(
      Collection<String> typeCodes, String brandNormalized, String nameCompact);

  /**
   * 사이트가 상품명 앞에 브랜드를 붙여 둔 제품을 찾는다("롬앤 더 쥬시 래스팅 틴트"를 "더 쥬시 래스팅 틴트"로). 반대로 입력이 브랜드로 시작하면 브랜드를 뗀 이름으로도
   * 찾는다. 둘 다 공백을 무시해 비교한다. 정확 일치·공백 무시 일치가 없을 때만 쓴다.
   */
  default List<Product> findWithBrandPrefix(
      Collection<String> typeCodes, String brand, String name) {
    if (typeCodes.isEmpty()) {
      return List.of();
    }
    String brandCompact = CatalogTextNormalizer.compact(brand);
    String nameCompact = CatalogTextNormalizer.compact(name);
    String brandNormalized = CatalogTextNormalizer.normalize(brand);
    List<Product> found =
        findAllByTypeCodeInAndBrandNormalizedAndNameCompact(
            typeCodes, brandNormalized, brandCompact + nameCompact);
    if (found.isEmpty()
        && nameCompact.startsWith(brandCompact)
        && nameCompact.length() > brandCompact.length()) {
      found =
          findAllByTypeCodeInAndBrandNormalizedAndNameCompact(
              typeCodes, brandNormalized, nameCompact.substring(brandCompact.length()));
    }
    return found;
  }

  /** 회원이 쓴 이름의 별칭으로 찾는다(S15P31A306-517). 정확 일치·공백 무시 일치가 없을 때만 쓴다. */
  @EntityGraph(attributePaths = {"category", "type"})
  @Query(
      "select p from Product p where p.id in (select a.productId from ProductNameAlias a"
          + " where a.typeCode in :types and a.brandNormalized = :brand and a.nameCompact = :name)")
  List<Product> findAllByAlias(
      @Param("types") Collection<String> typeCodes,
      @Param("brand") String brandNormalized,
      @Param("name") String nameCompact);

  default List<Product> findByAlias(Collection<String> typeCodes, String brand, String name) {
    if (typeCodes.isEmpty()) {
      return List.of();
    }
    return findAllByAlias(
        typeCodes, CatalogTextNormalizer.normalize(brand), CatalogTextNormalizer.compact(name));
  }

  /**
   * 자동 완성 후보(S15P31A306-530): 브랜드+제품명(공백 제거)에 단어 패턴 {@code w1..w6}(LIKE, 이스케이프 문자 {@code !})이
   * **모두** 들어 있는 제품. 안 쓰는 칸은 {@code %}로 채운다. 카테고리·종류는 {@code null}이면 거르지 않는다.
   *
   * <p>정렬은 DB 가 정한다: 제품명이 {@code prefix}로 시작하는 것 → 짧은 제품명 → 제품명 순. 그래서 {@code Pageable}로 잘라도 상위 후보가
   * 남는다.
   */
  @EntityGraph(attributePaths = {"category", "type"})
  @Query(
      "select p from Product p where "
          + SUGGEST_KEY
          + " like :w1 escape '!' and "
          + SUGGEST_KEY
          + " like :w2 escape '!' and "
          + SUGGEST_KEY
          + " like :w3 escape '!' and "
          + SUGGEST_KEY
          + " like :w4 escape '!' and "
          + SUGGEST_KEY
          + " like :w5 escape '!' and "
          + SUGGEST_KEY
          + " like :w6 escape '!'"
          + SUGGEST_FILTER
          + SUGGEST_ORDER)
  List<Product> findSuggestions(
      @Param("w1") String w1,
      @Param("w2") String w2,
      @Param("w3") String w3,
      @Param("w4") String w4,
      @Param("w5") String w5,
      @Param("w6") String w6,
      @Param("prefix") String prefix,
      @Param("category") String categoryCode,
      @Param("type") String typeCode,
      Pageable pageable);

  /**
   * 별칭(회원이 쓴 이름)의 브랜드+별칭에 단어 패턴이 **모두** 들어 있는 별칭을 가진 제품. 정렬은 {@link #findSuggestions}와 같다. 같은 별칭 행
   * 하나가 모든 단어를 만족해야 한다.
   */
  @EntityGraph(attributePaths = {"category", "type"})
  @Query(
      "select p from Product p where p.id in (select a.productId from ProductNameAlias a where "
          + ALIAS_KEY
          + " like :w1 escape '!' and "
          + ALIAS_KEY
          + " like :w2 escape '!' and "
          + ALIAS_KEY
          + " like :w3 escape '!' and "
          + ALIAS_KEY
          + " like :w4 escape '!' and "
          + ALIAS_KEY
          + " like :w5 escape '!' and "
          + ALIAS_KEY
          + " like :w6 escape '!')"
          + SUGGEST_FILTER
          + SUGGEST_ORDER)
  List<Product> findSuggestionsByAlias(
      @Param("w1") String w1,
      @Param("w2") String w2,
      @Param("w3") String w3,
      @Param("w4") String w4,
      @Param("w5") String w5,
      @Param("w6") String w6,
      @Param("prefix") String prefix,
      @Param("category") String categoryCode,
      @Param("type") String typeCode,
      Pageable pageable);

  String SUGGEST_KEY = "concat(replace(p.brandNormalized, ' ', ''), p.nameCompact)";
  String ALIAS_KEY = "concat(replace(a.brandNormalized, ' ', ''), a.nameCompact)";
  String SUGGEST_FILTER =
      " and (:category is null or p.category.code = :category)"
          + " and (:type is null or p.type.code = :type)";
  String SUGGEST_ORDER =
      " order by case when p.nameCompact like :prefix escape '!' then 0 else 1 end,"
          + " length(p.nameCompact), p.nameCompact";
}
