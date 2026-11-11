package com.mairor.backend.history.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.web.PageQuery;
import com.mairor.backend.common.web.PageResponse;
import com.mairor.backend.history.dto.ReportSummaryResponse;
import com.mairor.backend.history.entity.HistoryRecord;
import com.mairor.backend.history.repository.HistoryRecordRepository;
import com.mairor.backend.photos.dto.PhotoResponse;
import com.mairor.backend.photos.entity.PhotoState;
import com.mairor.backend.photos.entity.StoredPhoto;
import com.mairor.backend.photos.repository.StoredPhotoRepository;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;
import org.springframework.data.domain.Slice;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

/**
 * 리포트 목록 · 상세(API-REPORT-001 · 002). 가이드 실행 완료(S15P31A306-395)가 남긴 {@code history_records}를 읽기만 한다.
 * S15P31A306-404.
 */
@Service
public class HistoryRecordQueryService {

  private final HistoryRecordRepository records;
  private final StoredPhotoRepository photos;
  private final ObjectMapper objectMapper;

  public HistoryRecordQueryService(
      HistoryRecordRepository records, StoredPhotoRepository photos, ObjectMapper objectMapper) {
    this.records = records;
    this.photos = photos;
    this.objectMapper = objectMapper;
  }

  /** 회원의 리포트 한 페이지. 완성 사진은 지금 읽을 수 있을(AVAILABLE) 때만 준다. */
  @Transactional(readOnly = true)
  public PageResponse<ReportSummaryResponse> list(UUID userId, PageQuery page) {
    Slice<HistoryRecord> slice = records.findPageByUserId(userId, page.toPageable());
    Map<UUID, PhotoResponse> available = availablePhotos(slice.getContent());
    List<ReportSummaryResponse> items =
        slice.getContent().stream()
            .map(
                record ->
                    ReportSummaryResponse.from(
                        record,
                        record.getCompletedPhotoId() == null
                            ? null
                            : available.get(record.getCompletedPhotoId())))
            .toList();
    return PageResponse.of(items, page, slice.hasNext());
  }

  /**
   * 리포트 상세. 완료할 때 저장한 스냅샷을 다시 조립하지 않고 그대로 준다(명세 · 서연 연동 계약).
   *
   * @throws BusinessException 404 {@code NOT_FOUND} — 없거나 다른 회원의 리포트
   */
  @Transactional(readOnly = true)
  public JsonNode get(UUID userId, UUID recordId) {
    HistoryRecord record =
        records
            .findByIdAndUserId(recordId, userId)
            .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
    return objectMapper.readTree(record.getRecordSnapshot());
  }

  private Map<UUID, PhotoResponse> availablePhotos(List<HistoryRecord> page) {
    Set<UUID> ids =
        page.stream()
            .map(HistoryRecord::getCompletedPhotoId)
            .filter(Objects::nonNull)
            .collect(Collectors.toSet());
    if (ids.isEmpty()) {
      return Map.of();
    }
    return photos.findAllById(ids).stream()
        .filter(photo -> photo.getState() == PhotoState.AVAILABLE)
        .collect(Collectors.toMap(StoredPhoto::getId, PhotoResponse::from));
  }
}
