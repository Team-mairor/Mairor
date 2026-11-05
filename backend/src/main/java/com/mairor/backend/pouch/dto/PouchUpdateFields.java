package com.mairor.backend.pouch.dto;

import com.mairor.backend.pouch.entity.RegistrationMode;
import java.util.UUID;

/** 필드 생략 상태를 보존한 검증 완료 PATCH 값. */
public record PouchUpdateFields(
    PatchValue<RegistrationMode> registrationMode,
    PatchValue<UUID> productId,
    PatchValue<UUID> shadeId,
    PatchValue<String> category,
    PatchValue<String> type,
    PatchValue<String> brand,
    PatchValue<String> name,
    PatchValue<String> shadeName,
    PatchValue<String> colorHex) {

  /** specified=false는 생략, specified=true/value=null은 허용된 명시적 null이다. */
  public record PatchValue<T>(boolean specified, T value) {

    public static <T> PatchValue<T> missing() {
      return new PatchValue<>(false, null);
    }

    public static <T> PatchValue<T> supplied(T value) {
      return new PatchValue<>(true, value);
    }
  }
}
