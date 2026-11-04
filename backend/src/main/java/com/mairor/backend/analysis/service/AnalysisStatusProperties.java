package com.mairor.backend.analysis.service;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * 분석 상태 응답 설정({@code app.analysis.status}).
 *
 * @param pollAfter 상태 조회를 폴링할 때 다음 조회까지 기다릴 시간({@code pollAfterSeconds}). SSE 를 못 쓸 때 FE 가 쓴다
 */
@ConfigurationProperties(prefix = "app.analysis.status")
public record AnalysisStatusProperties(@DefaultValue("3s") Duration pollAfter) {}
