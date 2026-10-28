package com.mairor.backend.common.ratelimit;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * 요청 제한 수치 ({@code app.rate-limit.*}). 용도별로 한도({@code limit})와 시간 창({@code window})을 따로 두며, 용도를
 * 추가하면 항목을 더한다.
 */
@Validated
@ConfigurationProperties(prefix = "app.rate-limit")
public record RateLimitProperties(
    @Valid @NotNull Rule emailAvailability, @Valid @NotNull Rule emailVerification) {

  /** 시간 창({@code window}) 안에 허용하는 요청 수({@code limit}). */
  public record Rule(@Min(1) int limit, @NotNull Duration window) {}
}
