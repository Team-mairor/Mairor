package com.mairor.backend.common.security;

import jakarta.validation.constraints.NotEmpty;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

/**
 * 허용 Origin 목록 ({@code app.security.allowed-origins}, 환경변수 {@code ALLOWED_ORIGINS}).
 *
 * <p>비어 있으면 앱이 기동하지 않는다. 기본값은 dev 프로파일에만 있어서, 운영에서 값을 빠뜨리면 조용히 모두 거절하거나 모두 허용하는 대신 시작 단계에서 드러난다.
 */
@Validated
@ConfigurationProperties(prefix = "app.security")
public record OriginProperties(
    @NotEmpty(message = "app.security.allowed-origins(ALLOWED_ORIGINS)를 설정해야 합니다.")
        List<String> allowedOrigins) {}
