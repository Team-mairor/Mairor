package com.mairor.backend.common.security;

import jakarta.validation.constraints.NotNull;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * 세션 수명 설정 ({@code app.session.*}). 서버 유휴 만료({@code spring.session.timeout})와 쿠키 최대 수명({@code
 * server.servlet.session.cookie.max-age})은 Boot 가 읽는 설정이라 여기 두지 않고 {@link SessionLifetimeConfig} 가
 * 함께 모은다.
 *
 * @param absoluteTimeout 절대 만료. 로그인 성공 시점부터 이 시간이 지나면 활동 중이어도 세션이 끝난다. 일반 요청으로 연장하지 않는다
 */
@Validated
@ConfigurationProperties(prefix = "app.session")
public record SessionLifetimeProperties(@NotNull Duration absoluteTimeout) {}
