package com.mairor.backend.pouch.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.pouch.dto.PouchItemResponse;
import com.mairor.backend.pouch.dto.PouchUpdateRequest;
import com.mairor.backend.pouch.dto.PouchUpdateResponse;
import com.mairor.backend.pouch.entity.PouchItem;
import com.mairor.backend.pouch.repository.PouchItemRepository;
import com.mairor.backend.pouch.repository.PouchVersionRepository;
import java.util.UUID;
import org.hibernate.exception.ConstraintViolationException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

/** 개인 파우치 수정. 회원·항목 잠금, 수정, 중복 검사, 버전 갱신을 원자적으로 처리한다. */
@Service
public class PouchUpdateService {

  private final PouchVersionRepository versions;
  private final PouchItemRepository items;
  private final PouchUpdateValidator validator;
  private final PouchUpdateCandidateBuilder candidateBuilder;

  public PouchUpdateService(
      PouchVersionRepository versions,
      PouchItemRepository items,
      PouchUpdateValidator validator,
      PouchUpdateCandidateBuilder candidateBuilder) {
    this.versions = versions;
    this.items = items;
    this.validator = validator;
    this.candidateBuilder = candidateBuilder;
  }

  @Transactional(isolation = Isolation.READ_COMMITTED)
  public PouchUpdateResponse update(UUID userId, UUID pouchItemId, PouchUpdateRequest request) {
    var fields = validator.validate(request);
    long currentVersion =
        versions.lockByUserId(userId).orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
    PouchItem current =
        items
            .findByIdAndUserIdForUpdate(pouchItemId, userId)
            .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND));
    PouchItem candidate = candidateBuilder.build(userId, current, fields);

    if (current.hasSameDetails(candidate)) {
      return new PouchUpdateResponse(PouchItemResponse.from(current), currentVersion);
    }

    if (items.existsByUserIdAndBrandNormalizedAndNameNormalizedAndShadeNameNormalizedAndIdNot(
        userId,
        candidate.getBrandNormalized(),
        candidate.getNameNormalized(),
        candidate.getShadeNameNormalized(),
        current.getId())) {
      throw duplicate();
    }

    try {
      current.replaceDetailsFrom(candidate);
      PouchItem saved = items.saveAndFlush(current);
      long nextVersion = versions.increment(userId);
      return new PouchUpdateResponse(PouchItemResponse.from(saved), nextVersion);
    } catch (DataIntegrityViolationException exception) {
      if (isDuplicateConstraint(exception)) throw duplicate();
      throw exception;
    }
  }

  private static boolean isDuplicateConstraint(Throwable error) {
    for (Throwable cause = error; cause != null; cause = cause.getCause()) {
      if (cause instanceof ConstraintViolationException violation
          && "23505".equals(violation.getSQLState())
          && PouchItem.DUPLICATE_UNIQUE.equalsIgnoreCase(violation.getConstraintName())) {
        return true;
      }
    }
    return false;
  }

  private static BusinessException duplicate() {
    return new BusinessException(
        HttpStatus.CONFLICT, "POUCH_DUPLICATE", "이미 같은 제품이 파우치에 등록되어 있습니다.");
  }
}
