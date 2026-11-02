package com.mairor.backend.users.repository;

import com.mairor.backend.users.entity.AuthProvider;
import com.mairor.backend.users.entity.UserIdentity;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserIdentityRepository extends JpaRepository<UserIdentity, UUID> {

  /** 제공자 계정으로 연결을 찾는다. 회원도 함께 읽어서 트랜잭션 밖에서 {@code getUser()} 를 써도 된다. */
  @EntityGraph(attributePaths = "user")
  Optional<UserIdentity> findByProviderAndProviderSubject(
      AuthProvider provider, String providerSubject);
}
