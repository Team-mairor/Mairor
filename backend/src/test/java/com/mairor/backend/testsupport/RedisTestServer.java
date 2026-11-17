package com.mairor.backend.testsupport;

import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.utility.DockerImageName;

/**
 * 스프링 컨텍스트 없이 Redis 구현을 직접 확인하는 테스트가 함께 쓰는 Redis. 처음 쓸 때 컨테이너를 한 번 띄우고, 테스트 JVM 이 끝나면
 * Testcontainers 가 정리한다. 운영과 같은 버전을 쓴다.
 */
public final class RedisTestServer {

  private static final GenericContainer<?> REDIS =
      new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine")).withExposedPorts(6379);

  private static StringRedisTemplate template;

  private RedisTestServer() {}

  public static synchronized StringRedisTemplate template() {
    if (template == null) {
      REDIS.start();
      LettuceConnectionFactory factory =
          new LettuceConnectionFactory(
              new RedisStandaloneConfiguration(REDIS.getHost(), REDIS.getMappedPort(6379)));
      factory.afterPropertiesSet();
      factory.start();
      StringRedisTemplate created = new StringRedisTemplate(factory);
      created.afterPropertiesSet();
      template = created;
    }
    return template;
  }

  /** 앞 테스트가 남긴 키를 모두 지운다. */
  public static void flush() {
    template()
        .execute(
            (RedisCallback<Void>)
                connection -> {
                  connection.serverCommands().flushDb();
                  return null;
                });
  }
}
