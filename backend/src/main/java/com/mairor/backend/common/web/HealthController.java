package com.mairor.backend.common.web;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** 헬스체크. AI 서버의 {@code GET /health} 와 같은 응답 형식을 쓴다. */
@Tag(name = "헬스체크", description = "서버가 떠 있는지 확인한다. 로그인 없이 호출할 수 있다.")
@RestController
public class HealthController {

  @Operation(summary = "서버 상태 확인", description = "서버가 떠 있으면 `UP` 을 돌려준다.")
  @GetMapping("/health")
  public Map<String, String> health() {
    return Map.of("status", "UP");
  }
}
