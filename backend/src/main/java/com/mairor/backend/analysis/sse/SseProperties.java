package com.mairor.backend.analysis.sse;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * 분석 상태 SSE 설정({@code app.analysis.sse}).
 *
 * @param timeout 연결 하나를 열어 두는 최대 시간. 지나면 서버가 닫고 FE 의 EventSource 가 다시 붙는다. 정하지 않으면 Tomcat 기본값(30초)에
 *     끊긴다
 * @param pingInterval 빈 신호({@code : ping}) 간격. ALB·nginx 는 60초 동안 오가는 게 없으면 연결을 끊는다
 * @param reconcileInterval 열린 작업들의 상태를 DB 로 다시 맞추는 간격. 변경 알림을 놓쳐도 이 시간 안에 맞춰진다
 * @param listenPollTimeout LISTEN 연결에서 알림을 한 번 기다리는 시간. 끊김을 알아채는 간격이기도 하다
 * @param listenRetryMax LISTEN 연결이 끊겼을 때 다시 붙기 전 기다리는 최대 시간(1초부터 두 배씩)
 */
@ConfigurationProperties(prefix = "app.analysis.sse")
public record SseProperties(
    @DefaultValue("30m") Duration timeout,
    @DefaultValue("20s") Duration pingInterval,
    @DefaultValue("30s") Duration reconcileInterval,
    @DefaultValue("10s") Duration listenPollTimeout,
    @DefaultValue("30s") Duration listenRetryMax) {}
