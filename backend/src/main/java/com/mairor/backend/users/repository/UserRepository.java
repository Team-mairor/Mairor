package com.mairor.backend.users.repository;

import com.mairor.backend.users.entity.User;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserRepository extends JpaRepository<User, UUID> {

  /** 정규화한 이메일로 가입 여부를 확인한다. */
  boolean existsByEmail(String email);

  /** 정규화한 이메일로 회원을 조회한다. */
  Optional<User> findByEmail(String email);
}
