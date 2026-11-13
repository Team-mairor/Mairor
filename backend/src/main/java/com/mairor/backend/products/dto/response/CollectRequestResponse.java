package com.mairor.backend.products.dto.response;

import com.mairor.backend.products.entity.CatalogCollectRequest;
import com.mairor.backend.products.entity.CatalogCollectRequestUser;
import com.mairor.backend.products.entity.CollectRequestStatus;
import com.mairor.backend.products.entity.CollectTrigger;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

/** 화장품 수집 요청 하나와 요청한 회원들의 자동 연결 결과(운영 확인용). */
public record CollectRequestResponse(
    @Schema(description = "요청 ID(수집 워커 작업 ID)") UUID requestId,
    @Schema(description = "계기: USER(직접 입력 등록)·GUIDE(영상 분석)", example = "USER")
        CollectTrigger trigger,
    @Schema(
            description = "상태: QUEUED·SENT·RESOLVED·UNRESOLVED·NOT_FOUND·FAILED",
            example = "RESOLVED")
        CollectRequestStatus status,
    @Schema(description = "해결되지 않은 사유", example = "SEARCH_EMPTY", nullable = true) String reason,
    @Schema(description = "브랜드", example = "롬앤") String brand,
    @Schema(description = "찾을 제품 이름. 상품 주소로 다시 수집하면 없다", example = "쥬시 래스팅 틴트", nullable = true)
        String name,
    @Schema(description = "다시 수집할 상품 주소", nullable = true) String productUrl,
    @Schema(description = "요청한 호수 이름", example = "01 니어", nullable = true) String shadeName,
    @Schema(description = "큐에 보낸 횟수(실패 포함)", example = "1") int sendAttempts,
    @Schema(description = "수집 워커가 알린 상태", example = "COLLECTED", nullable = true)
        String resultStatus,
    @Schema(description = "수집 결과 파일 이름", nullable = true) String resultFile,
    @Schema(description = "요청을 만든 시각") Instant createdAt,
    @Schema(description = "큐에 보낸 시각", nullable = true) Instant sentAt,
    @Schema(description = "끝난 시각", nullable = true) Instant finishedAt,
    @Schema(description = "요청한 회원과 자동 연결 결과") List<Requester> requesters) {

  public record Requester(
      @Schema(description = "회원 ID") UUID userId,
      @Schema(description = "자동 연결 대상 파우치 항목. 지워졌으면 없다", nullable = true) UUID pouchItemId,
      @Schema(
              description = "자동 연결 결과: LINKED 또는 연결하지 않은 사유. 판정 전이면 없다",
              example = "LINKED",
              nullable = true)
          String linkResult) {

    static Requester from(CatalogCollectRequestUser row) {
      return new Requester(row.getUserId(), row.getPouchItemId(), row.getLinkResult());
    }
  }

  public static CollectRequestResponse of(
      CatalogCollectRequest request, List<CatalogCollectRequestUser> requesters) {
    return new CollectRequestResponse(
        request.getId(),
        request.getTrigger(),
        request.getStatus(),
        request.getReason(),
        request.getBrand(),
        request.getName(),
        request.getProductUrl(),
        request.getShadeName(),
        request.getSendAttempts(),
        request.getResultStatus(),
        request.getResultFile(),
        request.getCreatedAt(),
        request.getSentAt(),
        request.getFinishedAt(),
        requesters.stream().map(Requester::from).toList());
  }
}
