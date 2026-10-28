package com.mairor.backend.users.support;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 회원가입 정책 설정 ({@code app.signup.*}).
 *
 * @param requireEmailVerification {@code true}면 가입에 이메일 인증 토큰({@code emailVerificationToken})이
 *     필요하다. 기본 {@code false}
 */
@ConfigurationProperties(prefix = "app.signup")
public record SignupProperties(boolean requireEmailVerification) {}
