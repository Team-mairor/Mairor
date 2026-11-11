package com.mairor.backend.analysis.service;

import com.mairor.backend.analysis.dto.response.AnalysisJobSummaryResponse;
import com.mairor.backend.analysis.entity.AnalysisStatus;
import com.mairor.backend.analysis.repository.AnalysisJobRequestRecordRepository;
import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.error.ErrorResponse;
import com.mairor.backend.common.web.PageQuery;
import com.mairor.backend.common.web.PageResponse;
import com.mairor.backend.guides.entity.ReviewStatus;
import java.util.EnumSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import org.springframework.data.domain.Slice;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 내 분석 목록(API-VIDEO-007). 회원이 요청하거나 합류한 작업 중 분석이 끝난 것을 가이드 검수 상태로 골라 준다. 홈의 '검수 중 가이드' 카드에 쓴다. */
@Service
public class AnalysisJobListService {

  /** 검수 상태를 고르지 않았을 때. 반려(REJECTED)는 카드에서 빠지므로 고를 때만 준다. */
  static final Set<ReviewStatus> DEFAULT_REVIEW_STATUSES =
      EnumSet.of(ReviewStatus.PENDING, ReviewStatus.APPROVED);

  private static final Set<ReviewStatus> SELECTABLE =
      EnumSet.of(ReviewStatus.PENDING, ReviewStatus.APPROVED, ReviewStatus.REJECTED);

  private final AnalysisJobRequestRecordRepository requests;

  AnalysisJobListService(AnalysisJobRequestRecordRepository requests) {
    this.requests = requests;
  }

  /**
   * 회원의 분석 목록 한 페이지.
   *
   * @param reviewStatuses 고를 검수 상태. 비어 있으면 PENDING · APPROVED
   * @throws BusinessException 400 {@code VALIDATION_FAILED} — 고를 수 없는 검수 상태(NOT_READY)
   */
  @Transactional(readOnly = true)
  public PageResponse<AnalysisJobSummaryResponse> list(
      UUID userId, List<ReviewStatus> reviewStatuses, PageQuery page) {
    Slice<AnalysisJobSummaryView> slice =
        requests.findSummaries(
            userId, AnalysisStatus.COMPLETED, selected(reviewStatuses), page.toPageable());
    List<AnalysisJobSummaryResponse> items =
        slice.getContent().stream().map(AnalysisJobSummaryResponse::from).toList();
    return PageResponse.of(items, page, slice.hasNext());
  }

  private static Set<ReviewStatus> selected(List<ReviewStatus> reviewStatuses) {
    if (reviewStatuses == null) {
      return DEFAULT_REVIEW_STATUSES;
    }
    List<ReviewStatus> given = reviewStatuses.stream().filter(Objects::nonNull).toList();
    if (given.isEmpty()) {
      return DEFAULT_REVIEW_STATUSES;
    }
    if (!SELECTABLE.containsAll(given)) {
      throw new BusinessException(
          ErrorCode.VALIDATION_FAILED.status(),
          ErrorCode.VALIDATION_FAILED.name(),
          ErrorCode.VALIDATION_FAILED.message(),
          List.of(
              new ErrorResponse.FieldError(
                  "reviewStatus", "PENDING · APPROVED · REJECTED 중에서 고릅니다.")),
          null);
    }
    return EnumSet.copyOf(given);
  }
}
