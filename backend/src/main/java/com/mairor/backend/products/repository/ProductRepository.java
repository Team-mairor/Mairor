package com.mairor.backend.products.repository;

import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.support.CatalogTextNormalizer;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

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

  /** 수집 출처의 상품 번호로 찾는다. 같은 출처의 같은 번호는 한 제품이다({@code uk_products_source_product}). */
  @EntityGraph(attributePaths = {"category", "type"})
  Optional<Product> findBySourceAndSourceProductId(String source, String sourceProductId);

  /** 정규화된 값으로 찾는다. 정규화 전 값으로는 {@link #findExact}를 쓴다. */
  @EntityGraph(attributePaths = {"category", "type"})
  Optional<Product> findByTypeCodeAndBrandNormalizedAndNameNormalized(
      String typeCode, String brandNormalized, String nameNormalized);

  /** 제품명 공백을 무시한 후보를 모두 찾는다. 다중 결과는 호출부에서 모호한 검색으로 처리한다. */
  @EntityGraph(attributePaths = {"category", "type"})
  List<Product> findAllByTypeCodeAndBrandNormalizedAndNameCompact(
      String typeCode, String brandNormalized, String nameCompact);

  default List<Product> findCompact(String typeCode, String brand, String name) {
    return findAllByTypeCodeAndBrandNormalizedAndNameCompact(
        typeCode, CatalogTextNormalizer.normalize(brand), CatalogTextNormalizer.compact(name));
  }
}
