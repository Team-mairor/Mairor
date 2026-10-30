package com.mairor.backend.users.support;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import java.time.Duration;
import org.hibernate.validator.constraints.time.DurationMin;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * 가입 이메일 인증 정책 ({@code app.email-verification.*}).
 *
 * @param secret 인증번호 해시용 비밀키. 비우면 서버를 켤 때마다 임의로 만든다({@link VerificationHasher})
 * @param codeTtl 인증번호 유효 시간 (0보다 길어야 한다. 0 이면 만들자마자 만료된다)
 * @param resendCooldown 재발송 간격 (0 이상. 0 은 간격 없음)
 * @param hourlyLimit 이메일 하나당 시간당 발송 횟수
 * @param maxAttempts 인증번호를 틀릴 수 있는 횟수 (넘으면 재발송 필요)
 * @param tokenTtl 인증 완료 토큰 유효 시간 (0보다 길어야 한다)
 */
@Validated
@ConfigurationProperties(prefix = "app.email-verification")
public record EmailVerificationProperties(
    String secret,
    @NotNull @DurationMin(nanos = 0, inclusive = false) Duration codeTtl,
    @NotNull @DurationMin(nanos = 0) Duration resendCooldown,
    @Min(1) int hourlyLimit,
    @Min(1) int maxAttempts,
    @NotNull @DurationMin(nanos = 0, inclusive = false) Duration tokenTtl) {}
