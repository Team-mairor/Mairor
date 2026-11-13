package com.mairor.backend.products.collect;

import com.mairor.backend.products.dto.response.CollectRequestResponse;
import com.mairor.backend.products.entity.CatalogCollectRequest;
import com.mairor.backend.products.entity.CatalogCollectRequestUser;
import com.mairor.backend.products.entity.CollectRequestStatus;
import com.mairor.backend.products.repository.CatalogCollectRequestRepository;
import com.mairor.backend.products.repository.CatalogCollectRequestUserRepository;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 운영 확인용 수집 요청 목록. 요청과 요청자를 쿼리 두 번으로 읽는다. */
@Service
@Transactional(readOnly = true)
public class CollectRequestQueryService {

  private final CatalogCollectRequestRepository requests;
  private final CatalogCollectRequestUserRepository requesters;

  public CollectRequestQueryService(
      CatalogCollectRequestRepository requests, CatalogCollectRequestUserRepository requesters) {
    this.requests = requests;
    this.requesters = requesters;
  }

  /** 최근 요청부터 {@code limit}개. {@code status}가 없으면 모든 상태. */
  public List<CollectRequestResponse> recent(CollectRequestStatus status, int limit) {
    PageRequest page = PageRequest.of(0, limit);
    List<CatalogCollectRequest> found =
        status == null
            ? requests.findAllByOrderByCreatedAtDescIdDesc(page)
            : requests.findByStatusOrderByCreatedAtDescIdDesc(status, page);
    if (found.isEmpty()) {
      return List.of();
    }
    Map<UUID, List<CatalogCollectRequestUser>> byRequest =
        requesters
            .findByRequestIdInOrderByCreatedAtAsc(
                found.stream().map(CatalogCollectRequest::getId).toList())
            .stream()
            .collect(Collectors.groupingBy(CatalogCollectRequestUser::getRequestId));
    return found.stream()
        .map(r -> CollectRequestResponse.of(r, byRequest.getOrDefault(r.getId(), List.of())))
        .toList();
  }
}
