package com.mairor.backend.photos.entity;

/** AVAILABLE 사진만 읽을 수 있다. 파일 삭제 실패는 CLEANUP_PENDING으로 남겨 재시도한다. */
public enum PhotoState {
  PENDING_UPLOAD,
  AVAILABLE,
  CLEANUP_PENDING,
  DELETED
}
