package com.mairor.backend.products.repository;

import com.mairor.backend.products.entity.ProductNameAlias;
import com.mairor.backend.products.support.CatalogTextNormalizer;
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductNameAliasRepository extends JpaRepository<ProductNameAlias, UUID> {

  /** 별칭을 남긴다. 같은 키가 이미 있으면 처음 것을 둔다(0건). */
  @Modifying
  @Query(
      value =
          "insert into product_name_aliases (id, type_code, brand_normalized, name_compact,"
              + " product_id, request_id, created_at) values (gen_random_uuid(), :type, :brand,"
              + " :name, :product, :request, :now)"
              + " on conflict (type_code, brand_normalized, name_compact) do nothing",
      nativeQuery = true)
  int insertIfAbsent(
      @Param("type") String typeCode,
      @Param("brand") String brandNormalized,
      @Param("name") String nameCompact,
      @Param("product") UUID productId,
      @Param("request") UUID requestId,
      @Param("now") Instant now);

  /** 정규화 전 브랜드·제품명으로 남긴다. */
  default int remember(
      String typeCode, String brand, String name, UUID productId, UUID requestId, Instant now) {
    return insertIfAbsent(
        typeCode,
        CatalogTextNormalizer.normalize(brand),
        CatalogTextNormalizer.compact(name),
        productId,
        requestId,
        now);
  }
}
