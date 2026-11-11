package com.mairor.backend.common.external.ai;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/**
 * AI 서버 가이드 생성 설정 ({@code app.ai}). 형식은 {@code docs/references/ai-api.md}.
 *
 * @param baseUrl AI 서버 주소. 운영은 {@code core} 네트워크의 {@code http://ai:8000}
 * @param callbackBaseUrl AI 가 콜백을 보낼 BE 주소(context-path 포함). 운영은 nginx 를 거치지 않는 {@code
 *     http://api:8080/api}
 * @param connectTimeout 연결 시간 제한
 * @param readTimeout 응답 시간 제한. 접수(202)는 바로 오지만 요청 본문(프레임 URL 목록)이 커서 넉넉히 둔다
 * @param frameUrlTtl 프레임 사전 서명 URL 의 만료. AI 는 작업을 시작할 때 내려받는다
 * @param callbackTimeout 콜백을 기다리는 시간. 지나면 AI 에 상태를 묻는다
 * @param watchInterval 콜백 시간 초과를 확인하는 간격(worker)
 * @param sendFrames 요청에 레퍼런스 프레임을 실을지. 비우면({@code null}) 저장소가 http 주소를 줄 때만 싣는다(로컬 저장소는 싣지 않음)
 */
@ConfigurationProperties(prefix = "app.ai")
public record AiProperties(
    @DefaultValue("http://localhost:8000") String baseUrl,
    @DefaultValue("http://localhost:8080/api") String callbackBaseUrl,
    @DefaultValue("5s") Duration connectTimeout,
    @DefaultValue("2m") Duration readTimeout,
    @DefaultValue("24h") Duration frameUrlTtl,
    @DefaultValue("60m") Duration callbackTimeout,
    @DefaultValue("60s") Duration watchInterval,
    Boolean sendFrames) {}
