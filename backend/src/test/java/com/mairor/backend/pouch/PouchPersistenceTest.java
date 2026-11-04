package com.mairor.backend.pouch;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.pouch.entity.PouchColor;
import com.mairor.backend.pouch.entity.PouchItem;
import com.mairor.backend.pouch.entity.RegistrationMode;
import com.mairor.backend.pouch.repository.PouchItemRepository;
import com.mairor.backend.pouch.repository.PouchVersionRepository;
import com.mairor.backend.users.entity.User;
import com.mairor.backend.users.repository.UserRepository;
import jakarta.persistence.EntityManager;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.annotation.Transactional;

@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql",
      "app.security.allowed-origins=http://localhost:3000"
    })
@Transactional
class PouchPersistenceTest {

  @Autowired private PouchItemRepository items;
  @Autowired private PouchVersionRepository versions;
  @Autowired private UserRepository users;
  @Autowired private EntityManager em;
  @Autowired private JdbcTemplate jdbc;
  private UUID userId;

  @BeforeEach
  void setUp() {
    userId = users.saveAndFlush(new User("pouch@example.com", "hash")).getId();
    jdbc.update("insert into product_categories values ('LIP', '립', true, true, 1)");
    jdbc.update(
        "insert into product_types values ('LIPSTICK', 'LIP', '립스틱', 1), ('LIP_TINT', 'LIP', '틴트', 2)");
  }

  @Test
  void sqlValidatesAndMaximumLengthDisplayTextRoundTrips() {
    PouchItem item =
        items.saveAndFlush(
            manual(
                userId,
                "LIPSTICK",
                " " + "B".repeat(100) + " ",
                " " + "N".repeat(200) + " ",
                " " + "S".repeat(100) + " "));
    em.clear();
    PouchItem found = items.findByIdAndUserId(item.getId(), userId).orElseThrow();
    assertThat(found.getBrand()).hasSize(100);
    assertThat(found.getName()).hasSize(200);
    assertThat(found.getShadeName()).hasSize(100);
    assertThat(found.getCreatedAt()).isNotNull();
    assertThat(found.getUpdatedAt()).isNotNull();
    assertThat(found.getColor()).isNull();
    assertThat(items.findByIdAndUserId(item.getId(), UUID.randomUUID())).isEmpty();
  }

  @Test
  void normalizedDuplicateAcrossTypesAndMissingShadesViolatesNamedConstraint() {
    items.saveAndFlush(manual(userId, "LIPSTICK", " A  B ", "E\u0301 Lip", null));

    assertThatThrownBy(
            () -> items.saveAndFlush(manual(userId, "LIP_TINT", "a b", "É lip", "\u00a0")))
        .isInstanceOf(DataIntegrityViolationException.class)
        .hasMessageContaining(PouchItem.DUPLICATE_UNIQUE);
  }

  @Test
  void anotherUserCanOwnTheSameProductAndShade() {
    UUID other = users.saveAndFlush(new User("other-pouch@example.com", "hash")).getId();
    items.saveAndFlush(manual(userId, "LIPSTICK", "Brand", "Name", null));
    PouchItem item = items.saveAndFlush(manual(other, "LIPSTICK", "Brand", "Name", null));
    assertThat(item.getId()).isNotNull();
    assertThat(
            items.existsByUserIdAndBrandNormalizedAndNameNormalizedAndShadeNameNormalized(
                other, "brand", "name", ""))
        .isTrue();
  }

  @Test
  void catalogAndManualWithSameTextAlsoConflict() {
    UUID product = catalogProduct();
    items.saveAndFlush(
        new PouchItem(
            userId,
            RegistrationMode.CATALOG,
            product,
            null,
            "LIP",
            "LIPSTICK",
            "Brand",
            "Name",
            null,
            null));

    assertThatThrownBy(() -> items.saveAndFlush(manual(userId, "LIP_TINT", "Brand", "Name", null)))
        .hasMessageContaining(PouchItem.DUPLICATE_UNIQUE);
  }

  @Test
  void catalogChangesCannotRefreshThePersonalSnapshotOrVersion() {
    UUID product = catalogProduct();
    PouchItem item =
        items.saveAndFlush(
            new PouchItem(
                userId,
                RegistrationMode.CATALOG,
                product,
                null,
                "LIP",
                "LIPSTICK",
                "Brand",
                "Name",
                null,
                PouchColor.catalog("#112233", false)));
    jdbc.update(
        "update products set name = 'Changed', name_normalized = 'changed' where id = ?", product);
    em.clear();

    PouchItem found = items.findByIdAndUserId(item.getId(), userId).orElseThrow();
    assertThat(found.getName()).isEqualTo("Name");
    assertThat(found.getNameNormalized()).isEqualTo("name");
    assertThat(found.getColor()).isEqualTo(PouchColor.catalog("#112233", false));
    assertThat(versions.findByUserId(userId).orElseThrow()).isZero();
  }

  @Test
  void referencedCatalogCannotBeCascadeDeleted() {
    UUID product = catalogProduct();
    items.saveAndFlush(
        new PouchItem(
            userId,
            RegistrationMode.CATALOG,
            product,
            null,
            "LIP",
            "LIPSTICK",
            "Brand",
            "Name",
            null,
            null));

    assertThatThrownBy(() -> jdbc.update("delete from products where id = ?", product))
        .hasMessageContaining("fk_pouch_items_product");
  }

  @Test
  void databaseRejectsPartialColorAndModeOriginMismatch() {
    PouchItem item = items.saveAndFlush(manual(userId, "LIPSTICK", "Brand", "Name", null));
    assertThatThrownBy(
            () ->
                jdbc.update(
                    "update pouch_items set color_hex = '#112233' where id = ?", item.getId()))
        .hasMessageContaining("ck_pouch_items_color");
  }

  @Test
  void databaseRejectsManualColorThatClaimsToBeCatalog() {
    PouchItem item = items.saveAndFlush(manual(userId, "LIPSTICK", "Brand", "Name", null));
    assertThatThrownBy(
            () ->
                jdbc.update(
                    "update pouch_items set color_hex = '#112233', color_source = 'CATALOG', color_estimated = true where id = ?",
                    item.getId()))
        .hasMessageContaining("ck_pouch_items_color");
  }

  @Test
  void databaseRejectsInvalidCategoryTypePair() {
    PouchItem item = items.saveAndFlush(manual(userId, "LIPSTICK", "Brand", "Name", null));
    assertThatThrownBy(
            () ->
                jdbc.update(
                    "update pouch_items set category_code = 'BASE' where id = ?", item.getId()))
        .hasMessageContaining("fk_pouch_items_category_type");
  }

  @Test
  void versionStartsAtZeroAndCannotBeOverwrittenByStaleUserMerge() {
    User stale = users.findById(userId).orElseThrow();
    em.detach(stale);
    assertThat(stale.getPouchVersion()).isZero();
    assertThat(versions.lockByUserId(userId).orElseThrow()).isZero();
    assertThat(versions.increment(userId)).isEqualTo(1L);
    ReflectionTestUtils.setField(stale, "nickname", "새 닉네임");
    users.saveAndFlush(stale);
    users.updatePassword(userId, "new-hash", Instant.now());
    assertThat(versions.findByUserId(userId).orElseThrow()).isEqualTo(1L);
    em.clear();
    assertThat(users.findById(userId).orElseThrow().getPouchVersion()).isEqualTo(1L);
    assertThat(users.findById(userId).orElseThrow().getNickname()).isEqualTo("새 닉네임");
    assertThat(versions.findByUserId(UUID.randomUUID())).isEmpty();
  }

  @Test
  void pouchVersionDefaultsForRawUserInsertsAndIsBigint() {
    jdbc.update(
        "insert into users (id, email, provider, created_at, updated_at) values (gen_random_uuid(), 'raw-pouch@example.com', 'LOCAL', now(), now())");
    assertThat(
            jdbc.queryForObject(
                "select pouch_version from users where email = 'raw-pouch@example.com'",
                Long.class))
        .isZero();
    assertThat(
            jdbc.queryForObject(
                "select data_type from information_schema.columns where table_name = 'users' and column_name = 'pouch_version'",
                String.class))
        .isEqualTo("bigint");
    List<String> constraints =
        jdbc.queryForList(
            "select conname from pg_constraint where conrelid = 'pouch_items'::regclass",
            String.class);
    assertThat(constraints)
        .contains(
            PouchItem.DUPLICATE_UNIQUE,
            "fk_pouch_items_user",
            "fk_pouch_items_shade",
            "ck_pouch_items_mode");
  }

  private UUID catalogProduct() {
    UUID id = UUID.randomUUID();
    jdbc.update(
        "insert into products (id, brand, name, brand_normalized, name_normalized, category_code, type_code, created_at, updated_at) values (?, 'Brand', 'Name', 'brand', 'name', 'LIP', 'LIPSTICK', now(), now())",
        id);
    return id;
  }

  private PouchItem manual(UUID owner, String type, String brand, String name, String shade) {
    return new PouchItem(
        owner, RegistrationMode.MANUAL, null, null, "LIP", type, brand, name, shade, null);
  }
}
