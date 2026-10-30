package com.mairor.backend.common.security;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * 만료된 세션을 지우는 정리 작업 설정 ({@code app.session.sweep.*}). Spring Session 의 기본 정리 작업은 꺼 두었고({@code
 * spring.session.jdbc.cleanup-cron: "-"}) 이 작업이 대신 한다. 지우기 전에 종료 훅({@link SessionEndHook})을 호출하기
 * 위해서다.
 *
 * @param enabled {@code false} 면 정리 작업을 예약하지 않는다. 그러면 만료된 세션 행이 아무도 지우지 않아 쌓이므로 테스트나 점검 용도로만 끈다
 * @param interval 정리 작업 실행 간격. 이전 실행이 끝난 뒤부터 센다
 * @param batchSize 한 번 실행에서 정리를 시도하는 세션 수의 상한. 넘으면 다음 실행에서 이어서 한다
 * @param retryDelay 정리에 실패한 세션(훅 또는 삭제 실패)을 다시 시도하기까지 기다리는 시간. 그동안은 건너뛰어서 실패하는 세션이 뒤의 정상 세션을 막지 않는다
 */
@Validated
@ConfigurationProperties(prefix = "app.session.sweep")
public record SessionSweepProperties(
    boolean enabled,
    @NotNull Duration interval,
    @Min(1) int batchSize,
    @NotNull Duration retryDelay) {}
