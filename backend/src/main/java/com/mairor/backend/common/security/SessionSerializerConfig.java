package com.mairor.backend.common.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ResourceLoader;
import org.springframework.data.redis.serializer.JdkSerializationRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializer;
import org.springframework.data.redis.serializer.SerializationException;

/**
 * Spring Session Redis 가 세션 속성을 바이트로 바꿀 때 쓰는 직렬화기. Spring Session 이 기본으로 쓰는 것과 같은 Java 직렬화이고, 읽는 쪽의
 * 실패만 {@link UnreadableSessionException} 으로 감싸는 점이 다르다.
 *
 * <p>Spring Session 은 {@code springSessionDefaultRedisSerializer} 라는 이름의 {@link RedisSerializer} 빈이
 * 있으면 기본 구성 대신 그것을 쓴다. 쓰는 쪽(저장)의 실패는 감싸지 않고 그대로 둔다. 직렬화할 수 없는 값을 넣은 코드 버그가 "손상된 세션"으로 오해받지 않게 하려는
 * 것이다({@link SessionStoreFailureFilter}).
 */
@Configuration
public class SessionSerializerConfig {

  /** Spring Session 이 이 이름으로 찾는다. */
  static final String BEAN_NAME = "springSessionDefaultRedisSerializer";

  @Bean(BEAN_NAME)
  RedisSerializer<Object> springSessionDefaultRedisSerializer(ResourceLoader resourceLoader) {
    return create(resourceLoader.getClassLoader());
  }

  static RedisSerializer<Object> create(ClassLoader classLoader) {
    return new ReadFailureAware(new JdkSerializationRedisSerializer(classLoader));
  }

  private record ReadFailureAware(RedisSerializer<Object> delegate)
      implements RedisSerializer<Object> {

    @Override
    public byte[] serialize(Object value) {
      return delegate.serialize(value);
    }

    @Override
    public Object deserialize(byte[] bytes) {
      try {
        return delegate.deserialize(bytes);
      } catch (SerializationException e) {
        throw new UnreadableSessionException("저장된 세션 값을 읽지 못했습니다.", e);
      }
    }
  }
}
