package com.mairor.backend.pouch.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.pouch.dto.PouchItemResponse;
import com.mairor.backend.pouch.dto.PouchRegistrationRequest;
import com.mairor.backend.pouch.dto.PouchRegistrationResponse;
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

/** 개인 파우치 등록. 회원 잠금·저장·버전 증가를 한 READ_COMMITTED 트랜잭션으로 처리한다. */
@Service
public class PouchRegistrationService {

  private final PouchVersionRepository versions;
  private final PouchItemRepository items;
  private final PouchRegistrationValidator validator;

  public PouchRegistrationService(
      PouchVersionRepository versions,
      PouchItemRepository items,
      PouchRegistrationValidator validator) {
    this.versions = versions;
    this.items = items;
    this.validator = validator;
  }

  @Transactional(isolation = Isolation.READ_COMMITTED)
  public PouchRegistrationResponse register(UUID userId, PouchRegistrationRequest request) {
    if (versions.lockByUserId(userId).isEmpty()) {
      throw new BusinessException(HttpStatus.NOT_FOUND, "NOT_FOUND", "회원을 찾을 수 없습니다.");
    }

    PouchItem item = validator.prepare(userId, request);
    if (items.existsByUserIdAndBrandNormalizedAndNameNormalizedAndShadeNameNormalized(
        userId,
        item.getBrandNormalized(),
        item.getNameNormalized(),
        item.getShadeNameNormalized())) {
      throw duplicate();
    }

    try {
      PouchItem saved = items.saveAndFlush(item);
      long pouchVersion = versions.increment(userId);
      return new PouchRegistrationResponse(PouchItemResponse.from(saved), pouchVersion);
    } catch (DataIntegrityViolationException e) {
      if (isDuplicateConstraint(e)) throw duplicate();
      throw e;
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
