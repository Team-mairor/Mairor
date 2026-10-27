package com.mairor.backend.users.repository;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.users.entity.User;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.transaction.annotation.Transactional;

@Import(TestcontainersConfiguration.class)
@SpringBootTest
@Transactional
class UserRepositoryTest {

  @Autowired private UserRepository userRepository;

  @Test
  void save_generatesIdAndTimestamps() {
    User saved = userRepository.saveAndFlush(new User("member@example.com", "{bcrypt}hash"));

    assertThat(saved.getId()).isNotNull();
    assertThat(saved.getCreatedAt()).isNotNull();
    assertThat(saved.getUpdatedAt()).isNotNull();
    assertThat(saved.getPasswordHash()).isEqualTo("{bcrypt}hash");
  }

  @Test
  void save_allowsMissingPasswordHash() {
    User saved = userRepository.saveAndFlush(new User("google-only@example.com", null));

    assertThat(userRepository.findById(saved.getId()))
        .get()
        .extracting(User::getPasswordHash)
        .isNull();
  }

  @Test
  void existsByEmail_matchesStoredEmail() {
    userRepository.saveAndFlush(new User("member@example.com", "{bcrypt}hash"));

    assertThat(userRepository.existsByEmail("member@example.com")).isTrue();
    assertThat(userRepository.existsByEmail("other@example.com")).isFalse();
  }

  @Test
  void save_duplicateEmail_violatesNamedUniqueConstraint() {
    userRepository.saveAndFlush(new User("member@example.com", "{bcrypt}hash"));

    assertThatThrownBy(
            () -> userRepository.saveAndFlush(new User("member@example.com", "{bcrypt}other")))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(User.EMAIL_UNIQUE);
  }
}
