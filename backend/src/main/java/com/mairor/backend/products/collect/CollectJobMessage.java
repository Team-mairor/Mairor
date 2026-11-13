package com.mairor.backend.products.collect;

import com.mairor.backend.products.entity.CatalogCollectRequest;
import java.time.Instant;
import java.util.UUID;

/**
 * 수집 큐에 넣는 작업 메시지(CollectJob). 계약은 {@code shared/catalog-import/README.md}와 {@code
 * collect_job.v1.schema.json}이다. {@code jobId}는 요청 id 이고, 같은 jobId 는 워커가 한 번만 반영한다.
 *
 * @param typeHint 소분류 코드. 주면 워커가 모델로 종류를 고르지 않는다
 */
public record CollectJobMessage(
    int contractVersion,
    String jobId,
    String brand,
    String name,
    String url,
    String typeHint,
    Instant requestedAt) {

  public static final int CONTRACT_VERSION = 1;

  public static CollectJobMessage of(CatalogCollectRequest request) {
    UUID id = request.getId();
    return new CollectJobMessage(
        CONTRACT_VERSION,
        id.toString(),
        request.getBrand(),
        request.getName(),
        request.getProductUrl(),
        request.getTypeCode(),
        request.getCreatedAt());
  }
}
