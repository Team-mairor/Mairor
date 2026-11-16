package com.mairor.backend.pouch.service;

import com.mairor.backend.common.error.BusinessException;
import com.mairor.backend.pouch.entity.PouchItem;
import org.hibernate.exception.ConstraintViolationException;
import org.springframework.http.HttpStatus;

/** 등록·수정에서 같은 파우치 중복 항목을 동일한 오류로 처리한다. */
final class PouchDuplicateHandling {

  private PouchDuplicateHandling() {}

  static boolean isDuplicateConstraint(Throwable error) {
    for (Throwable cause = error; cause != null; cause = cause.getCause()) {
      if (cause instanceof ConstraintViolationException violation
          && "23505".equals(violation.getSQLState())
          && PouchItem.DUPLICATE_UNIQUE.equalsIgnoreCase(violation.getConstraintName())) {
        return true;
      }
    }
    return false;
  }

  static BusinessException duplicate() {
    return new BusinessException(
        HttpStatus.CONFLICT, "POUCH_DUPLICATE", "이미 같은 제품이 파우치에 등록되어 있습니다.");
  }
}
