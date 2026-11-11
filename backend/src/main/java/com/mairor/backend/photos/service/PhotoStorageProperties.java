package com.mairor.backend.photos.service;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

/** 업로드 중단 복구와 파일 정리용 기술 설정. 연결된 얼굴 사진의 보관 기간과는 별개다. */
@Validated
@ConfigurationProperties("app.photos")
public record PhotoStorageProperties(
    @DefaultValue("10m") @NotNull Duration stagingTimeout,
    @DefaultValue("1m") @NotNull Duration cleanupInterval,
    @DefaultValue("1m") @NotNull Duration cleanupRetryDelay,
    @DefaultValue("50") @Min(1) int cleanupBatchSize,
    @DefaultValue("25000000") @Min(1) long maxDecodedPixels,
    @DefaultValue("true") boolean cleanupEnabled) {
  @AssertTrue(message = "사진 업로드/정리 시간은 양수여야 한다")
  public boolean isDurationsPositive() {
    return positive(stagingTimeout) && positive(cleanupInterval) && positive(cleanupRetryDelay);
  }

  private static boolean positive(Duration value) {
    return value != null && !value.isNegative() && !value.isZero();
  }
}
