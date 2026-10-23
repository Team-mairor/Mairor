package com.mairor.backend.common.security;

import com.mairor.backend.common.error.ErrorCode;
import com.mairor.backend.common.error.ErrorResponseWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.SecurityFilterChain;

/**
 * 보안 설정. 헬스체크만 열고 나머지는 인증을 요구한다. 미인증은 401, CSRF·권한 실패는 403을 공통 오류 형식(JSON)으로 응답한다.
 *
 * <p>세션 로그인·CSRF 토큰 전달·회원 가입/로그인 경로 공개는 회원 이슈(서연)에서 이 설정에 덧붙인다.
 */
@Configuration
@EnableWebSecurity
public class SecurityConfig {

  @Bean
  SecurityFilterChain securityFilterChain(HttpSecurity http, ErrorResponseWriter errorWriter)
      throws Exception {
    http.authorizeHttpRequests(
            auth ->
                auth.requestMatchers("/health", "/actuator/health", "/actuator/health/**")
                    .permitAll()
                    .anyRequest()
                    .authenticated())
        .exceptionHandling(
            ex ->
                ex.authenticationEntryPoint(
                        (request, response, e) ->
                            errorWriter.write(response, ErrorCode.UNAUTHORIZED))
                    .accessDeniedHandler(
                        (request, response, e) -> errorWriter.write(response, ErrorCode.FORBIDDEN)))
        .csrf(Customizer.withDefaults())
        .httpBasic(AbstractHttpConfigurer::disable)
        .formLogin(AbstractHttpConfigurer::disable);
    return http.build();
  }
}
