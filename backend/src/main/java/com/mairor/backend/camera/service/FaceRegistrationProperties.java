package com.mairor.backend.camera.service;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties("app.face-registration")
public record FaceRegistrationProperties(
    @DefaultValue("v1") @NotBlank @Size(max = 50) String noticeVersion,
    @DefaultValue("1m") @NotNull Duration cleanupInterval,
    @DefaultValue("50") @Min(1) int cleanupBatchSize,
    @DefaultValue("true") boolean orphanCleanupEnabled) {
  @AssertTrue(message = "얼굴 등록 정리 주기는 양수여야 한다")
  public boolean isCleanupIntervalPositive() {
    return cleanupInterval != null && !cleanupInterval.isZero() && !cleanupInterval.isNegative();
  }
}
