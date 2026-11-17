package com.mairor.backend.users.support;

import com.mairor.backend.testsupport.RedisTestServer;
import java.time.Duration;

/** 인메모리와 같은 테스트를 실제 Redis 로 돌린다. */
class RedisGoogleSignupStoreTest extends GoogleSignupStoreTest {

  @Override
  GoogleSignupStore create(Duration ttl) {
    RedisTestServer.flush();
    return new GoogleSignupStore(ttl, RedisTestServer.template());
  }
}
