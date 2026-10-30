package com.mairor.backend.common.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.ConversionService;
import org.springframework.core.convert.support.GenericConversionService;
import org.springframework.core.io.ResourceLoader;
import org.springframework.core.serializer.support.DeserializingConverter;
import org.springframework.core.serializer.support.SerializationFailedException;
import org.springframework.core.serializer.support.SerializingConverter;

/**
 * Spring Session JDBC 가 세션 속성을 바이트로 바꿀 때 쓰는 변환 서비스. Spring Session 이 기본으로 만드는 것과 같은 구성(Java 직렬화)이고,
 * 읽는 쪽의 실패만 {@link UnreadableSessionException} 으로 감싸는 점이 다르다.
 *
 * <p>Spring Session 은 {@code springSessionConversionService} 라는 이름의 {@link ConversionService} 빈이
 * 있으면 기본 구성 대신 그것을 쓴다. 쓰는 쪽(저장)의 실패는 감싸지 않고 그대로 둔다. 직렬화할 수 없는 값을 넣은 코드 버그가 "손상된 세션"으로 오해받지 않게 하려는
 * 것이다({@link SessionStoreFailureFilter}).
 */
@Configuration
public class SessionConversionConfig {

  /** Spring Session 이 이 이름으로 찾는다. */
  static final String BEAN_NAME = "springSessionConversionService";

  @Bean(BEAN_NAME)
  ConversionService springSessionConversionService(ResourceLoader resourceLoader) {
    return create(resourceLoader.getClassLoader());
  }

  static GenericConversionService create(ClassLoader classLoader) {
    GenericConversionService conversion = new GenericConversionService();
    conversion.addConverter(Object.class, byte[].class, new SerializingConverter());
    DeserializingConverter deserializer = new DeserializingConverter(classLoader);
    conversion.addConverter(
        byte[].class,
        Object.class,
        stored -> {
          try {
            return deserializer.convert(stored);
          } catch (SerializationFailedException e) {
            throw new UnreadableSessionException("저장된 세션 값을 읽지 못했습니다.", e);
          }
        });
    return conversion;
  }
}
