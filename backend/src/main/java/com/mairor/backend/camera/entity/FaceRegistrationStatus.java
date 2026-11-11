package com.mairor.backend.camera.entity;

/** 폐기된 등록은 discardedAt으로 접근을 차단하고 API에서 404로 처리한다. */
public enum FaceRegistrationStatus {
  REGISTERED,
  LINKED,
  RETAINED
}
