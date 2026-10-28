package com.mairor.backend.users.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.doThrow;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.users.SignUpRequests;
import com.mairor.backend.users.repository.UserAgreementRepository;
import com.mairor.backend.users.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

/**
 * 회원과 약관 동의 기록은 한 트랜잭션이라, 약관 저장이 실패하면 회원도 남지 않아야 한다. 테스트 자체를 트랜잭션으로 감싸면 서비스의 트랜잭션이 바깥에 합류해 이 확인이
 * 의미가 없어지므로 {@code @Transactional}을 붙이지 않는다. 이 테스트는 데이터를 남기지 않는다(성공해야 할 저장이 없다).
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class UserSignUpRollbackTest {

  @Autowired private UserSignUpService service;
  @Autowired private UserRepository userRepository;

  @MockitoSpyBean private UserAgreementRepository userAgreementRepository;

  @Test
  void whenSavingAgreementsFails_theUserIsNotSavedEither() {
    doThrow(new DataIntegrityViolationException("agreements failed"))
        .when(userAgreementRepository)
        .saveAllAndFlush(anyList());

    assertThatThrownBy(
            () ->
                service.signUp(
                    SignUpRequests.basic(
                        "rollback@example.com", "ExampleOnly!2026", "ExampleOnly!2026")))
        .isInstanceOf(DataIntegrityViolationException.class);

    assertThat(userRepository.existsByEmail("rollback@example.com")).isFalse();
  }
}
