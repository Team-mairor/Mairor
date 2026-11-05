package com.mairor.backend.pouch.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.web.PageQuery;
import com.mairor.backend.common.web.PageResponse;
import com.mairor.backend.pouch.dto.PouchItemResponse;
import com.mairor.backend.pouch.dto.PouchListQuery;
import com.mairor.backend.pouch.dto.PouchListResponse;
import com.mairor.backend.pouch.repository.PouchItemRepository;
import com.mairor.backend.pouch.repository.PouchVersionRepository;
import java.util.UUID;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

/** 로그인 회원의 개인 파우치 목록·상세 조회(API-POUCH-003·005). */
@Service
public class PouchQueryService {

  private final PouchItemRepository items;
  private final PouchVersionRepository versions;
  private final PouchQueryValidator validator;

  public PouchQueryService(
      PouchItemRepository items, PouchVersionRepository versions, PouchQueryValidator validator) {
    this.items = items;
    this.versions = versions;
    this.validator = validator;
  }

  @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
  public PouchListResponse list(UUID userId, PouchListQuery filters, PageQuery page) {
    validator.validate(filters);

    var rows =
        items.findPageForUser(
            userId, filters.category(), filters.type(), PageRequest.of(page.page(), page.size()));
    var responsePage = rows.map(PouchItemResponse::from);
    long pouchVersion =
        versions.findByUserId(userId).orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));

    return PouchListResponse.of(PageResponse.of(responsePage), pouchVersion);
  }

  @Transactional(readOnly = true)
  public PouchItemResponse get(UUID userId, UUID pouchItemId) {
    return items
        .findByIdAndUserId(pouchItemId, userId)
        .map(PouchItemResponse::from)
        .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
  }
}
