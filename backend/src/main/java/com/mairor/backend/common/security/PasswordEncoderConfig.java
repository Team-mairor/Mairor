package com.mairor.backend.common.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

/**
 * 비밀번호 인코더. 해시 앞에 알고리즘 식별자를 붙여({@code {bcrypt}$2a$10$...}) 저장하므로, 나중에 알고리즘을 바꿔도 기존 해시를 그대로 검증할 수
 * 있다. 새로 만드는 해시는 bcrypt(비용 10)다.
 */
@Configuration
public class PasswordEncoderConfig {

  @Bean
  PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
  }
}
