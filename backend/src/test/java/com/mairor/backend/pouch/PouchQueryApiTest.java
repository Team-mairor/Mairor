package com.mairor.backend.pouch;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.doAnswer;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.authentication;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.common.web.PageQuery;
import com.mairor.backend.pouch.dto.PouchListQuery;
import com.mairor.backend.pouch.dto.PouchListResponse;
import com.mairor.backend.pouch.entity.PouchItem;
import com.mairor.backend.pouch.entity.RegistrationMode;
import com.mairor.backend.pouch.repository.PouchItemRepository;
import com.mairor.backend.pouch.repository.PouchVersionRepository;
import com.mairor.backend.pouch.service.PouchQueryService;
import com.mairor.backend.users.support.AuthenticatedUser;
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
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.RequestPostProcessor;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

/** 내 파우치 목록·상세 API의 소유권, 필터, 페이지·버전 계약을 PostgreSQL로 확인한다. */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql,classpath:db/schema/executions.sql",
      "app.security.allowed-origins=http://localhost:3000"
    })
@AutoConfigureMockMvc
class PouchQueryApiTest {

  private static final String PATH = "/v1/users/me/pouch-items";

  @Autowired private MockMvc mockMvc;
  @Autowired private JdbcTemplate jdbc;
  @Autowired private PouchItemRepository items;
  @MockitoSpyBean private PouchVersionRepository versions;
  @Autowired private PouchQueryService queryService;
  @Autowired private PlatformTransactionManager transactionManager;

  private UUID userId;
  private UUID otherUserId;
  private String category;
  private String otherCategory;
  private String type;
  private String otherType;

  @BeforeEach
  void setUp() {
    userId = UUID.randomUUID();
    otherUserId = UUID.randomUUID();
    String suffix = UUID.randomUUID().toString().replace("-", "").substring(0, 8).toUpperCase();
    category = "PQU" + suffix;
    otherCategory = "PQX" + suffix;
    type = category + "_TYPE";
    otherType = otherCategory + "_TYPE";

    for (UUID id : List.of(userId, otherUserId)) {
      jdbc.update(
          "insert into users (id, email, provider, created_at, updated_at) values (?, ?, 'LOCAL', now(), now())",
          id,
          id + "@example.com");
    }
    jdbc.update(
        "insert into product_categories values (?, '파우치 시험 분류', true, true, 1), (?, '다른 파우치 시험 분류', true, true, 2)",
        category,
        otherCategory);
    jdbc.update(
        "insert into product_types values (?, ?, '시험 종류', 1), (?, ?, '다른 종류', 1)",
        type,
        category,
        otherType,
        otherCategory);
  }

  @AfterEach
  void cleanUp() {
    jdbc.update("delete from pouch_items where user_id in (?, ?)", userId, otherUserId);
    jdbc.update("delete from product_types where code in (?, ?)", type, otherType);
    jdbc.update("delete from product_categories where code in (?, ?)", category, otherCategory);
    jdbc.update("delete from users where id in (?, ?)", userId, otherUserId);
  }

  @Test
  void emptyPouchReturnsPageMetadataAndCurrentVersionWithoutCaching() throws Exception {
    mockMvc
        .perform(get(PATH).with(asMember(userId)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items").isEmpty())
        .andExpect(jsonPath("$.page").value(0))
        .andExpect(jsonPath("$.size").value(20))
        .andExpect(jsonPath("$.hasNext").value(false))
        .andExpect(jsonPath("$.pouchVersion").value(0))
        .andExpect(
            header()
                .string(
                    HttpHeaders.CACHE_CONTROL, org.hamcrest.Matchers.containsString("no-store")));
  }

  @Test
  void listFiltersByOwnerCategoryAndTypeAndPaginatesWithHasNext() throws Exception {
    UUID lipOne = save(userId, category, type, "Lip one");
    UUID lipTwo = save(userId, category, type, "Lip two");
    save(userId, otherCategory, otherType, "Other category");
    save(otherUserId, category, type, "Other member");
    jdbc.update(
        "update pouch_items set created_at = '2026-01-01T00:00:00Z'::timestamptz where user_id = ? and category_code = ?",
        userId,
        category);
    String expectedFirst =
        lipTwo.toString().compareTo(lipOne.toString()) > 0 ? "Lip two" : "Lip one";
    String expectedSecond = expectedFirst.equals("Lip two") ? "Lip one" : "Lip two";

    mockMvc
        .perform(
            get(PATH)
                .queryParam("category", category)
                .queryParam("type", type)
                .queryParam("page", "0")
                .queryParam("size", "1")
                .with(asMember(userId)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items.length()").value(1))
        .andExpect(jsonPath("$.items[0].category").value(category))
        .andExpect(jsonPath("$.items[0].type").value(type))
        .andExpect(jsonPath("$.items[0].name").value(expectedFirst))
        .andExpect(jsonPath("$.hasNext").value(true))
        .andExpect(jsonPath("$.pouchVersion").value(0));

    mockMvc
        .perform(
            get(PATH)
                .queryParam("category", category)
                .queryParam("type", type)
                .queryParam("page", "1")
                .queryParam("size", "1")
                .with(asMember(userId)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items.length()").value(1))
        .andExpect(jsonPath("$.items[0].name").value(expectedSecond))
        .andExpect(jsonPath("$.hasNext").value(false));

    mockMvc
        .perform(get(PATH).queryParam("category", category).with(asMember(userId)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items.length()").value(2));

    mockMvc
        .perform(get(PATH).queryParam("type", otherType).with(asMember(userId)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items.length()").value(1))
        .andExpect(jsonPath("$.items[0].category").value(otherCategory));
  }

  @Test
  void invalidCategoryTypeAndPageValuesReturnFieldErrors() throws Exception {
    mockMvc
        .perform(get(PATH).queryParam("category", "UNKNOWN_CATEGORY").with(asMember(userId)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.details[0].field").value("category"));

    mockMvc
        .perform(get(PATH).queryParam("type", "UNKNOWN_TYPE").with(asMember(userId)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("type"));

    mockMvc
        .perform(
            get(PATH)
                .queryParam("category", category)
                .queryParam("type", otherType)
                .with(asMember(userId)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("type"));

    mockMvc
        .perform(get(PATH).queryParam("page", "-1").with(asMember(userId)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("page"));

    mockMvc
        .perform(get(PATH).queryParam("size", "101").with(asMember(userId)))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.details[0].field").value("size"));
  }

  @Test
  void detailHidesOtherMembersItemsAndReturnsTheSameNotFoundCode() throws Exception {
    UUID ownItem = save(userId, category, type, "My item");
    UUID otherItem = save(otherUserId, category, type, "Other item");

    mockMvc
        .perform(get(PATH + "/" + ownItem).with(asMember(userId)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.pouchItemId").value(ownItem.toString()))
        .andExpect(jsonPath("$.name").value("My item"));

    mockMvc
        .perform(get(PATH + "/" + otherItem).with(asMember(userId)))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOT_FOUND"));

    mockMvc
        .perform(get(PATH + "/" + UUID.randomUUID()).with(asMember(userId)))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.code").value("NOT_FOUND"));
  }

  @Test
  void listRequiresAuthentication() throws Exception {
    mockMvc
        .perform(get(PATH))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
  }

  @Test
  void repeatableReadKeepsItemsAndVersionAtTheSameSnapshotDuringAConcurrentWrite()
      throws Exception {
    CountDownLatch versionRead = new CountDownLatch(1);
    CountDownLatch writerCommitted = new CountDownLatch(1);

    doAnswer(
            invocation -> {
              assertThat(TransactionSynchronizationManager.getCurrentTransactionIsolationLevel())
                  .isEqualTo(TransactionDefinition.ISOLATION_REPEATABLE_READ);
              versionRead.countDown();
              await(writerCommitted);
              return invocation.callRealMethod();
            })
        .when(versions)
        .findByUserId(userId);

    try (var pool = Executors.newSingleThreadExecutor()) {
      Future<PouchListResponse> snapshot =
          pool.submit(
              () -> queryService.list(userId, new PouchListQuery(null, null), PageQuery.first()));

      assertThat(versionRead.await(10, TimeUnit.SECONDS)).isTrue();
      TransactionTemplate writeTransaction = new TransactionTemplate(transactionManager);
      writeTransaction.executeWithoutResult(
          status -> {
            items.saveAndFlush(item(userId, category, type, "Concurrent item"));
            versions.increment(userId);
          });
      writerCommitted.countDown();

      var oldSnapshot = snapshot.get(10, TimeUnit.SECONDS);
      assertThat(oldSnapshot.items()).isEmpty();
      assertThat(oldSnapshot.pouchVersion()).isZero();
      assertThat(
              queryService
                  .list(userId, new PouchListQuery(null, null), PageQuery.first())
                  .pouchVersion())
          .isEqualTo(1L);
    }
  }

  private UUID save(UUID owner, String categoryCode, String typeCode, String name) {
    PouchItem saved = items.saveAndFlush(item(owner, categoryCode, typeCode, name));
    return saved.getId();
  }

  private static PouchItem item(UUID owner, String categoryCode, String typeCode, String name) {
    return new PouchItem(
        owner,
        RegistrationMode.MANUAL,
        null,
        null,
        categoryCode,
        typeCode,
        "Test Brand",
        name,
        null,
        null);
  }

  private static RequestPostProcessor asMember(UUID id) {
    return authentication(
        UsernamePasswordAuthenticationToken.authenticated(
            new AuthenticatedUser(id, "member@example.com"),
            null,
            List.of(new SimpleGrantedAuthority("ROLE_USER"))));
  }

  private static void await(CountDownLatch latch) {
    try {
      if (!latch.await(10, TimeUnit.SECONDS)) {
        throw new IllegalStateException("동시성 테스트 시작 신호 대기 시간 초과");
      }
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new IllegalStateException("동시성 테스트가 중단됐다", e);
    }
  }
}
