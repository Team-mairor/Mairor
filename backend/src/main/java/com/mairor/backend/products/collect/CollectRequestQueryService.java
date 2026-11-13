package com.mairor.backend.products.collect;

import com.mairor.backend.products.dto.response.CollectRequestResponse;
import com.mairor.backend.products.entity.CatalogCollectRequest;
import com.mairor.backend.products.entity.CatalogCollectRequestGuide;
import com.mairor.backend.products.entity.CatalogCollectRequestUser;
import com.mairor.backend.products.entity.CollectRequestStatus;
import com.mairor.backend.products.repository.CatalogCollectRequestGuideRepository;
import com.mairor.backend.products.repository.CatalogCollectRequestRepository;
import com.mairor.backend.products.repository.CatalogCollectRequestUserRepository;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 운영 확인용 수집 요청 목록. 요청·요청자·기다리는 가이드 단계를 쿼리 세 번으로 읽는다. */
@Service
@Transactional(readOnly = true)
public class CollectRequestQueryService {

  private final CatalogCollectRequestRepository requests;
  private final CatalogCollectRequestUserRepository requesters;
  private final CatalogCollectRequestGuideRepository waitingSteps;

  public CollectRequestQueryService(
      CatalogCollectRequestRepository requests,
      CatalogCollectRequestUserRepository requesters,
      CatalogCollectRequestGuideRepository waitingSteps) {
    this.requests = requests;
    this.requesters = requesters;
    this.waitingSteps = waitingSteps;
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
    List<UUID> ids = found.stream().map(CatalogCollectRequest::getId).toList();
    Map<UUID, List<CatalogCollectRequestUser>> byRequest =
        requesters.findByRequestIdInOrderByCreatedAtAsc(ids).stream()
            .collect(Collectors.groupingBy(CatalogCollectRequestUser::getRequestId));
    Map<UUID, List<CatalogCollectRequestGuide>> stepsByRequest =
        waitingSteps.findByRequestIdInOrderByCreatedAtAsc(ids).stream()
            .collect(Collectors.groupingBy(CatalogCollectRequestGuide::getRequestId));
    return found.stream()
        .map(
            r ->
                CollectRequestResponse.of(
                    r,
                    byRequest.getOrDefault(r.getId(), List.of()),
                    stepsByRequest.getOrDefault(r.getId(), List.of())))
        .toList();
  }
}
