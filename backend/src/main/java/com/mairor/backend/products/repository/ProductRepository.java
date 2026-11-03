package com.mairor.backend.products.repository;

import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.support.CatalogTextNormalizer;
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

  /** 정규화된 값으로 찾는다. 정규화 전 값으로는 {@link #findExact}를 쓴다. */
  @EntityGraph(attributePaths = {"category", "type"})
  Optional<Product> findByTypeCodeAndBrandNormalizedAndNameNormalized(
      String typeCode, String brandNormalized, String nameNormalized);
}
