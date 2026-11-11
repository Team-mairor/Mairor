package com.mairor.backend.users.repository;

import com.mairor.backend.users.entity.User;
import jakarta.persistence.LockModeType;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.transaction.annotation.Transactional;

public interface UserRepository extends JpaRepository<User, UUID> {

  /** 정규화한 이메일로 가입 여부를 확인한다. */
  boolean existsByEmail(String email);

  /** 정규화한 이메일로 회원을 조회한다. */
  Optional<User> findByEmail(String email);

  /** 회원 소유 리소스의 생성/교체를 짧은 쓰기 트랜잭션에서 직렬화한다. */
  @Lock(LockModeType.PESSIMISTIC_WRITE)
  @Query("select u from User u where u.id = :id")
  Optional<User> findByIdForUpdate(@Param("id") UUID id);

  /**
   * 회원의 현재 비밀번호 버전. 로그인이 세션을 발급한 뒤, 비밀번호를 확인할 때 읽어 둔 값과 같은지 다시 확인하는 데 쓴다. 엔티티를 거치지 않고 값 하나만 읽는다.
   *
   * @return 회원이 없으면 비어 있다
   */
  @Query("select u.passwordVersion from User u where u.id = :id")
  Optional<Integer> findPasswordVersionById(@Param("id") UUID id);

  /**
   * 비밀번호 해시를 바꾸고 비밀번호 버전을 1 올린다. 엔티티를 읽어 고치지 않고 한 문장으로 갱신해서, 동시에 바꿔도 증가분을 잃지 않는다.
   *
   * @param updatedAt 수정 시각. 직접 갱신 쿼리는 {@code @UpdateTimestamp}가 동작하지 않아 호출자가 넘긴다
   * @return 바뀐 행 수. 회원이 없으면 0
   */
  @Transactional
  @Modifying(flushAutomatically = true, clearAutomatically = true)
  @Query(
      "update User u set u.passwordHash = :passwordHash,"
          + " u.passwordVersion = u.passwordVersion + 1, u.updatedAt = :updatedAt"
          + " where u.id = :id")
  int updatePassword(
      @Param("id") UUID id,
      @Param("passwordHash") String passwordHash,
      @Param("updatedAt") Instant updatedAt);
}
