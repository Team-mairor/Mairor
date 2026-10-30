package com.mairor.backend.common.error;

import static org.assertj.core.api.Assertions.assertThat;

import java.sql.SQLException;
import java.sql.SQLNonTransientConnectionException;
import java.sql.SQLTransientConnectionException;
import org.hibernate.TransactionException;
import org.hibernate.exception.JDBCConnectionException;
import org.junit.jupiter.api.Test;
import org.springframework.dao.CannotAcquireLockException;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.dao.QueryTimeoutException;
import org.springframework.jdbc.BadSqlGrammarException;
import org.springframework.jdbc.CannotGetJdbcConnectionException;
import org.springframework.orm.jpa.JpaSystemException;
import org.springframework.transaction.CannotCreateTransactionException;

class StoreFailureTest {

  @Test
  void connectionAndTransientFailuresAreUnavailable() {
    assertThat(StoreFailure.isUnavailable(new CannotGetJdbcConnectionException("pool"))).isTrue();
    assertThat(StoreFailure.isUnavailable(new DataAccessResourceFailureException("down"))).isTrue();
    assertThat(StoreFailure.isUnavailable(new QueryTimeoutException("slow"))).isTrue();
    assertThat(StoreFailure.isUnavailable(new CannotAcquireLockException("deadlock"))).isTrue();
  }

  @Test
  void failingToOpenATransactionIsUnavailable() {
    assertThat(
            StoreFailure.isUnavailable(
                new CannotCreateTransactionException(
                    "Could not open JPA EntityManager for transaction",
                    new JDBCConnectionException(
                        "Unable to acquire JDBC Connection", new SQLException("timeout")))))
        .isTrue();
  }

  /** 연결이 죽은 뒤 롤백까지 실패하면 스프링은 원래 예외를 롤백 예외로 덮어쓴다. 남는 것은 이 사슬뿐이다. */
  @Test
  void aFailedRollbackHidingTheOriginalErrorIsUnavailable() {
    Throwable masked =
        new JpaSystemException(
            new TransactionException(
                "Unable to rollback against JDBC Connection",
                new SQLException("Connection is closed")));

    assertThat(StoreFailure.isUnavailable(masked)).isTrue();
  }

  @Test
  void standardJdbcConnectionErrorsAreUnavailable() {
    assertThat(StoreFailure.isUnavailable(new SQLTransientConnectionException("hikari timeout")))
        .isTrue();
    assertThat(StoreFailure.isUnavailable(new SQLNonTransientConnectionException("closed")))
        .isTrue();
    assertThat(StoreFailure.isUnavailable(new SQLException("connection failure", "08006")))
        .isTrue();
  }

  @Test
  void anUnavailableCauseDeepInTheChainIsFound() {
    Throwable deep =
        new IllegalStateException(
            "wrapper", new RuntimeException(new SQLNonTransientConnectionException("closed")));

    assertThat(StoreFailure.isUnavailable(deep)).isTrue();
  }

  @Test
  void serverProblemsInTheDatabaseAreNotUnavailable() {
    assertThat(StoreFailure.isUnavailable(new BadSqlGrammarException("task", "select", null)))
        .isFalse();
    assertThat(StoreFailure.isUnavailable(new DataIntegrityViolationException("constraint")))
        .isFalse();
    assertThat(StoreFailure.isUnavailable(new DuplicateKeyException("duplicate"))).isFalse();
  }

  @Test
  void anUnclassifiedRawSqlExceptionIsNotUnavailable() {
    assertThat(StoreFailure.isUnavailable(new SQLException("something"))).isFalse();
    assertThat(StoreFailure.isUnavailable(new SQLException("duplicate key", "23505"))).isFalse();
    assertThat(StoreFailure.isUnavailable(new SQLException("no state"))).isFalse();
  }

  @Test
  void unrelatedExceptionsAreNotUnavailable() {
    assertThat(StoreFailure.isUnavailable(new IllegalStateException("bug"))).isFalse();
    assertThat(StoreFailure.isUnavailable(null)).isFalse();
  }

  @Test
  void aSelfReferencingCauseDoesNotLoopForever() {
    IllegalStateException loop =
        new IllegalStateException("loop") {
          @Override
          public synchronized Throwable getCause() {
            return this;
          }
        };

    assertThat(StoreFailure.isUnavailable(loop)).isFalse();
  }
}
