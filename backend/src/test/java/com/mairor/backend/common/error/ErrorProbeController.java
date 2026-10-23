package com.mairor.backend.common.error;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 테스트 전용: 각종 예외를 일부러 던져 {@link GlobalExceptionHandler}의 응답 형식을 검증한다. */
@RestController
@RequestMapping("/v1/error-probe")
@ConditionalOnProperty(name = "test.error-probe", havingValue = "true")
public class ErrorProbeController {

  record Sample(@NotBlank(message = "비어 있을 수 없습니다.") String name, @Min(1) int count) {}

  @GetMapping("/conflict")
  public void conflict() {
    throw new BusinessException(HttpStatus.CONFLICT, "ANALYSIS_IN_PROGRESS", "이미 분석 중인 영상입니다.");
  }

  @GetMapping("/limit")
  public void limit() {
    throw BusinessException.tooManyRequests(30);
  }

  @GetMapping("/missing")
  public void missing() {
    throw new BusinessException(ErrorCode.NOT_FOUND);
  }

  @GetMapping("/boom")
  public void boom() {
    throw new IllegalStateException("internal detail that must not leak");
  }

  @PostMapping("/body")
  public Sample body(@Valid @RequestBody Sample sample) {
    return sample;
  }
}
