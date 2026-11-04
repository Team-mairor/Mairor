package com.mairor.backend.pouch;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.pouch.entity.PouchItem;
import com.mairor.backend.pouch.entity.RegistrationMode;
import com.mairor.backend.pouch.repository.PouchItemRepository;
import com.mairor.backend.pouch.repository.PouchVersionRepository;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** 각 작업이 별도 연결·트랜잭션에서 커밋/롤백하도록 테스트 자체에는 트랜잭션을 걸지 않는다. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql",
      "app.security.allowed-origins=http://localhost:3000"
    })
class PouchWriteTransactionTest {

  @Autowired private PouchVersionRepository versions;
  @Autowired private PouchItemRepository items;
  @Autowired private JdbcTemplate jdbc;
  @Autowired private PlatformTransactionManager transactionManager;
  private TransactionTemplate tx;
  private final UUID userId = UUID.randomUUID();
  private final UUID otherId = UUID.randomUUID();

  @BeforeEach
  void setUp() {
    tx = new TransactionTemplate(transactionManager);
    tx.executeWithoutResult(
        status -> {
          for (UUID id : List.of(userId, otherId)) {
            jdbc.update(
                "insert into users (id, email, provider, created_at, updated_at) values (?, ?, 'LOCAL', now(), now())",
                id,
                id + "@example.com");
          }
          jdbc.update(
              "insert into product_categories values ('POUCH_TEST', '시험용', true, true, 100)");
          jdbc.update(
              "insert into product_types values ('POUCH_TEST_TYPE', 'POUCH_TEST', '시험용', 1)");
        });
  }

  @AfterEach
  void cleanUp() {
    tx.executeWithoutResult(
        status -> {
          jdbc.update("delete from pouch_items where user_id in (?, ?)", userId, otherId);
          jdbc.update("delete from users where id in (?, ?)", userId, otherId);
          jdbc.update("delete from product_types where code = 'POUCH_TEST_TYPE'");
          jdbc.update("delete from product_categories where code = 'POUCH_TEST'");
        });
  }

  @Test
  void locksAndIncrementsRequireTheCallersTransaction() {
    assertThatThrownBy(() -> versions.lockByUserId(userId))
        .isInstanceOf(IllegalTransactionStateException.class);
    assertThatThrownBy(() -> versions.increment(userId))
        .isInstanceOf(IllegalTransactionStateException.class);
  }

  @Test
  void itemAndVersionRollBackTogether() {
    assertThatThrownBy(
            () ->
                tx.executeWithoutResult(
                    status -> {
                      versions.lockByUserId(userId).orElseThrow();
                      items.saveAndFlush(item("Rollback"));
                      versions.increment(userId);
                      throw new IllegalStateException("rollback probe");
                    }))
        .hasMessage("rollback probe");

    assertThat(versions.findByUserId(userId).orElseThrow()).isZero();
    assertThat(countItems()).isZero();
  }

  @Test
  void concurrentWritesForOneMemberKeepEveryVersionIncrement() throws Exception {
    try (var pool = Executors.newFixedThreadPool(4)) {
      CountDownLatch go = new CountDownLatch(1);
      List<Future<Long>> results = new ArrayList<>();
      for (int i = 0; i < 4; i++) {
        String name = "Item " + i;
        results.add(
            pool.submit(
                () -> {
                  assertThat(go.await(10, TimeUnit.SECONDS)).isTrue();
                  return tx.execute(
                      status -> {
                        versions.lockByUserId(userId).orElseThrow();
                        items.saveAndFlush(item(name));
                        return versions.increment(userId);
                      });
                }));
      }
      go.countDown();
      List<Long> returnedVersions = new ArrayList<>();
      for (Future<Long> result : results) {
        returnedVersions.add(result.get(15, TimeUnit.SECONDS));
      }
      assertThat(returnedVersions).containsExactlyInAnyOrder(1L, 2L, 3L, 4L);
      assertThat(versions.findByUserId(userId).orElseThrow()).isEqualTo(4L);
      assertThat(countItems()).isEqualTo(4);
    }
  }

  @Test
  void concurrentDuplicateLeavesOnlyOneItemAndOneVersionIncrement() throws Exception {
    try (var pool = Executors.newFixedThreadPool(2)) {
      CountDownLatch go = new CountDownLatch(1);
      List<Future<Boolean>> results = new ArrayList<>();
      for (int i = 0; i < 2; i++) {
        results.add(
            pool.submit(
                () -> {
                  assertThat(go.await(10, TimeUnit.SECONDS)).isTrue();
                  try {
                    tx.executeWithoutResult(
                        status -> {
                          versions.lockByUserId(userId).orElseThrow();
                          items.saveAndFlush(item("Same"));
                          versions.increment(userId);
                        });
                    return true;
                  } catch (DataIntegrityViolationException duplicate) {
                    assertThat(duplicate).hasMessageContaining(PouchItem.DUPLICATE_UNIQUE);
                    return false;
                  }
                }));
      }
      go.countDown();
      assertThat(
              List.of(
                  results.get(0).get(15, TimeUnit.SECONDS),
                  results.get(1).get(15, TimeUnit.SECONDS)))
          .containsExactlyInAnyOrder(true, false);
      assertThat(countItems()).isEqualTo(1);
      assertThat(versions.findByUserId(userId).orElseThrow()).isEqualTo(1L);
    }
  }

  @Test
  void heldMemberLockBlocksThatMemberButNotAnotherMember() throws Exception {
    CountDownLatch locked = new CountDownLatch(1);
    CountDownLatch release = new CountDownLatch(1);
    try (var pool = Executors.newSingleThreadExecutor()) {
      Future<?> holder =
          pool.submit(
              () ->
                  tx.executeWithoutResult(
                      status -> {
                        versions.lockByUserId(userId).orElseThrow();
                        locked.countDown();
                        try {
                          if (!release.await(15, TimeUnit.SECONDS))
                            throw new IllegalStateException("lock test timed out");
                        } catch (InterruptedException interrupted) {
                          Thread.currentThread().interrupt();
                          throw new IllegalStateException(interrupted);
                        }
                      }));
      try {
        assertThat(locked.await(10, TimeUnit.SECONDS)).isTrue();
        assertThatThrownBy(
                () ->
                    tx.executeWithoutResult(
                        status -> {
                          jdbc.execute("set local lock_timeout = '250ms'");
                          versions.lockByUserId(userId);
                        }))
            .isInstanceOf(DataAccessException.class)
            .rootCause()
            .isInstanceOfSatisfying(
                SQLException.class, error -> assertThat(error.getSQLState()).isEqualTo("55P03"));
        Long otherVersion =
            tx.execute(
                status -> {
                  jdbc.execute("set local lock_timeout = '250ms'");
                  versions.lockByUserId(otherId).orElseThrow();
                  return versions.increment(otherId);
                });
        assertThat(otherVersion).isEqualTo(1L);
      } finally {
        release.countDown();
      }
      holder.get(10, TimeUnit.SECONDS);
    }
  }

  private PouchItem item(String name) {
    return new PouchItem(
        userId,
        RegistrationMode.MANUAL,
        null,
        null,
        "POUCH_TEST",
        "POUCH_TEST_TYPE",
        "Brand",
        name,
        null,
        null);
  }

  private int countItems() {
    return jdbc.queryForObject(
        "select count(*) from pouch_items where user_id = ?", Integer.class, userId);
  }
}
