package com.mairor.backend.users.repository;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.users.entity.AuthProvider;
import com.mairor.backend.users.entity.User;
import com.mairor.backend.users.entity.UserIdentity;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;

/** 트랜잭션 없이 실행해, 조회 결과의 회원을 트랜잭션 밖에서 읽을 수 있는지까지 확인한다. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class UserIdentityRepositoryTest {

  @Autowired private UserRepository userRepository;
  @Autowired private UserIdentityRepository identityRepository;
  @Autowired private JdbcTemplate jdbc;

  private final List<User> created = new ArrayList<>();

  @AfterEach
  void cleanUp() {
    for (User user : created) {
      jdbc.update("delete from user_identities where user_id = ?", user.getId());
      jdbc.update("delete from users where id = ?", user.getId());
    }
  }

  private User saveUser(String email) {
    User user = userRepository.saveAndFlush(new User(email, null));
    created.add(user);
    return user;
  }

  @Test
  void findByProviderAndSubject_returnsIdentityWithItsUserLoaded() {
    User user = saveUser("google@example.com");
    identityRepository.saveAndFlush(new UserIdentity(user, AuthProvider.GOOGLE, "google-sub-1"));

    UserIdentity found =
        identityRepository
            .findByProviderAndProviderSubject(AuthProvider.GOOGLE, "google-sub-1")
            .orElseThrow();

    assertThat(found.getCreatedAt()).isNotNull();
    // open-in-view 가 꺼져 있어도 회원을 함께 읽어 두었으므로 지연 로딩 오류가 나지 않는다
    assertThat(found.getUser().getEmail()).isEqualTo("google@example.com");
  }

  @Test
  void findByProviderAndSubject_isEmptyForUnknownSubject() {
    assertThat(identityRepository.findByProviderAndProviderSubject(AuthProvider.GOOGLE, "nobody"))
        .isEmpty();
  }

  @Test
  void sameSubjectCannotBeLinkedTwice() {
    User first = saveUser("first@example.com");
    User second = saveUser("second@example.com");
    identityRepository.saveAndFlush(new UserIdentity(first, AuthProvider.GOOGLE, "google-sub-1"));

    assertThatThrownBy(
            () ->
                identityRepository.saveAndFlush(
                    new UserIdentity(second, AuthProvider.GOOGLE, "google-sub-1")))
        .isInstanceOf(DataIntegrityViolationException.class);
  }
}
