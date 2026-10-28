package com.mairor.backend.common.mail;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 메일 발송 설정 ({@code app.mail.*}). SMTP 접속 정보({@code spring.mail.*})와 별개다.
 *
 * @param enabled {@code true}면 SMTP 로 실제 발송한다. {@code false}면 dev 는 로그로만 남기고 prod 는 발송하지 않는다
 * @param from 보내는 사람 주소. 비우면 SMTP 계정 주소를 쓴다
 * @param fromName 받는 사람에게 보이는 보내는 사람 이름
 */
@ConfigurationProperties(prefix = "app.mail")
public record AppMailProperties(boolean enabled, String from, String fromName) {}
