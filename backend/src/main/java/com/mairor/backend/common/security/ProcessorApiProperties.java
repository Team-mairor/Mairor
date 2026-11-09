package com.mairor.backend.common.security;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 영상 전처리 노트북 API({@code /v1/internal/processor/**}) 공유 토큰 ({@code app.processor.token}, 환경변수 {@code
 * PROCESSOR_API_TOKEN}, S15P31A306-357).
 *
 * <p>노트북이 {@code X-Processor-Token} 헤더로 보낸다. 운영자 토큰({@link InternalApiProperties})과 다른 값이어야 노트북 키가
 * 새도 운영자 API 가 열리지 않는다. 비어 있으면 노트북 API 는 모든 요청을 401 로 거절하고, 앱 기동은 막지 않는다.
 */
@ConfigurationProperties(prefix = "app.processor")
public record ProcessorApiProperties(String token) {}
