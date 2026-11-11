package com.mairor.backend.analysis.service;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * 영상 전처리 노트북 연결 설정({@code app.analysis.processor}, S15P31A306-357 · 358).
 *
 * @param enabled 연결 모드. 켜면 대기 작업을 노트북이 가져가고 worker 는 집지 않으며, 노트북이 끝낸 작업을 worker 가 AI 에 맡긴다. 끄면 노트북
 *     claim 은 늘 할 일 없음이고 worker 가 지금처럼 처리한다
 * @param lease 노트북 임대 시간. 이 안에 끝났다는 · 실패했다는 · 진행 알림이 없으면 다시 내준다
 * @param maxClaims 같은 작업을 몇 번까지 내줄지. 이만큼 가져간 작업의 임대가 또 지나면 재시도 가능 실패({@code PROCESSOR_TIMEOUT})로
 *     끝낸다
 * @param waitTimeout 아무 노트북도 가져가지 않은 대기 작업, 임대가 지나고 아무도 다시 가져가지 않은 작업을 이만큼 기다린 뒤 {@code
 *     PROCESSOR_TIMEOUT}으로 끝낸다(노트북 꺼짐)
 */
@ConfigurationProperties(prefix = "app.analysis.processor")
public record ProcessorProperties(
    @DefaultValue("false") boolean enabled,
    @DefaultValue("900s") Duration lease,
    @DefaultValue("2") int maxClaims,
    @DefaultValue("30m") Duration waitTimeout) {

  public ProcessorProperties {
    if (lease.isNegative() || lease.isZero()) {
      throw new IllegalArgumentException("app.analysis.processor.lease 는 0 보다 커야 합니다.");
    }
    if (maxClaims < 1) {
      throw new IllegalArgumentException("app.analysis.processor.max-claims 는 1 이상이어야 합니다.");
    }
    if (waitTimeout.isNegative() || waitTimeout.isZero()) {
      throw new IllegalArgumentException("app.analysis.processor.wait-timeout 은 0 보다 커야 합니다.");
    }
  }
}
