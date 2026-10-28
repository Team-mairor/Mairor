package com.mairor.backend.users.support;

import com.mairor.backend.users.entity.AgreementType;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * 서버의 현재 약관 버전 ({@code app.agreements.versions.*}). 필수 약관은 요청의 버전이 이 값과 같아야 하고, 마케팅(선택)은 요청의 버전을
 * 그대로 기록한다.
 */
@Validated
@ConfigurationProperties(prefix = "app.agreements")
public record AgreementProperties(@Valid @NotNull Versions versions) {

  public record Versions(
      @NotBlank String terms, @NotBlank String privacy, @NotBlank String ageOver14) {}

  /** 필수 약관의 현재 버전. 마케팅처럼 버전을 맞추지 않는 약관은 {@code null}. */
  public String currentVersion(AgreementType type) {
    return switch (type) {
      case TERMS -> versions.terms();
      case PRIVACY -> versions.privacy();
      case AGE_OVER_14 -> versions.ageOver14();
      case MARKETING -> null;
    };
  }
}
