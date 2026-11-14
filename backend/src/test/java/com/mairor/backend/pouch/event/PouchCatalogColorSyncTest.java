package com.mairor.backend.pouch.event;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.pouch.entity.PouchColor;
import com.mairor.backend.pouch.entity.PouchItem;
import com.mairor.backend.pouch.entity.RegistrationMode;
import com.mairor.backend.pouch.repository.PouchItemRepository;
import com.mairor.backend.products.entity.ColorSource;
import com.mairor.backend.products.entity.NameSource;
import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.entity.ProductCategory;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductType;
import com.mairor.backend.products.entity.ReviewStatus;
import com.mairor.backend.products.event.CatalogColorChanged;
import com.mairor.backend.users.entity.User;
import com.mairor.backend.users.repository.UserRepository;
import jakarta.persistence.EntityManager;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

/**
 * 카탈로그 색이 바뀌면 그 호수에 연결된 파우치 항목의 색 복사본이 맞춰지는지 실제 DB 로 본다(S15P31A306-531). 규칙: 쓸 수 있는 카탈로그 단색이 있으면
 * 회원이 넣은 색보다 그 색, 단색이 없어지면 카탈로그에서 복사한 색은 비우고 회원이 넣은 색은 둔다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql,classpath:db/schema/executions.sql",
      "app.security.allowed-origins=http://localhost:3000"
    })
@Transactional
class PouchCatalogColorSyncTest {

  @Autowired private ApplicationEventPublisher events;
  @Autowired private PouchItemRepository pouchItems;
  @Autowired private UserRepository users;
  @Autowired private JdbcTemplate jdbc;
  @Autowired private EntityManager em;

  private ProductType tint;
  private UUID userId;

  @BeforeEach
  void setUp() {
    ProductCategory lip = new ProductCategory("LIP", "립", true, true, 5);
    em.persist(lip);
    tint = new ProductType("LIP_TINT", lip, "립틴트", 1);
    em.persist(tint);
    userId = users.saveAndFlush(new User("sync@example.com", "hash")).getId();
  }

  private ProductShade shade(String productName, String hex, ReviewStatus status) {
    Product product = new Product(tint, "롬앤", productName);
    ProductShade shade = product.addShade("01 오리지널", 1, null);
    if (hex != null) {
      shade
          .addColor(1, null, NameSource.NONE)
          .assignColor(ColorSource.SAMPLE, hex, false, status, null);
    }
    em.persist(product);
    em.flush();
    return shade;
  }

  private PouchItem linkedItem(ProductShade shade, String name, PouchColor color) {
    PouchItem item =
        new PouchItem(
            userId,
            RegistrationMode.CATALOG,
            shade.getProduct().getId(),
            shade.getId(),
            "LIP",
            "LIP_TINT",
            "롬앤",
            name,
            "01 오리지널",
            color);
    return pouchItems.saveAndFlush(item);
  }

  private PouchItem changed(PouchItem item, ProductShade shade) {
    events.publishEvent(new CatalogColorChanged(Set.of(shade.getId())));
    em.flush();
    em.clear();
    return pouchItems.findById(item.getId()).orElseThrow();
  }

  private long version() {
    return jdbc.queryForObject("select pouch_version from users where id = ?", Long.class, userId);
  }

  @Test
  void aCatalogColorThatArrivesLaterFillsAnItemThatHadNone() {
    ProductShade shade = shade("블러 퍼지 틴트", "#BE5953", ReviewStatus.AUTO_APPROVED);
    PouchItem item = linkedItem(shade, "블러 퍼지 틴트", null);
    long before = version();

    PouchItem after = changed(item, shade);

    assertThat(after.getColor().getHex()).isEqualTo("#BE5953");
    assertThat(after.getColorSource()).isEqualTo("CATALOG");
    assertThat(version()).isEqualTo(before + 1);
  }

  @Test
  void theCatalogColorReplacesTheColorTheMemberTyped() {
    ProductShade shade = shade("블러 퍼지 틴트", "#BE5953", ReviewStatus.APPROVED);
    PouchItem item = linkedItem(shade, "블러 퍼지 틴트", PouchColor.userInput("#C0FFEE"));

    PouchItem after = changed(item, shade);

    assertThat(after.getColor().getHex()).isEqualTo("#BE5953");
    assertThat(after.getColorSource()).isEqualTo("CATALOG");
  }

  @Test
  void aColorThatIsNoLongerUsableClearsTheCatalogCopyButKeepsTheMembersColor() {
    ProductShade fromCatalog = shade("틴트 A", "#BE5953", ReviewStatus.BELOW_THRESHOLD);
    PouchItem copied = linkedItem(fromCatalog, "틴트 A", PouchColor.catalog("#BE5953", false));
    ProductShade typed = shade("틴트 B", "#BE5953", ReviewStatus.BELOW_THRESHOLD);
    PouchItem own = linkedItem(typed, "틴트 B", PouchColor.userInput("#C0FFEE"));

    PouchItem clearedCopy = changed(copied, fromCatalog);
    PouchItem keptOwn = changed(own, typed);

    assertThat(clearedCopy.getColor()).isNull();
    assertThat(keptOwn.getColor().getHex()).isEqualTo("#C0FFEE");
    assertThat(keptOwn.getColorSource()).isEqualTo("USER_INPUT");
  }

  @Test
  void aPaletteShadeIsNotGivenASingleColor() {
    Product product = new Product(tint, "롬앤", "팔레트 틴트");
    ProductShade shade = product.addShade("01 듀오", 1, null);
    shade
        .addColor(1, null, NameSource.NONE)
        .assignColor(ColorSource.SAMPLE, "#AA0000", false, ReviewStatus.AUTO_APPROVED, null);
    shade
        .addColor(2, null, NameSource.NONE)
        .assignColor(ColorSource.SAMPLE, "#00AA00", false, ReviewStatus.AUTO_APPROVED, null);
    em.persist(product);
    em.flush();
    PouchItem item = linkedItem(shade, "팔레트 틴트", PouchColor.userInput("#C0FFEE"));

    PouchItem after = changed(item, shade);

    assertThat(after.getColor().getHex()).isEqualTo("#C0FFEE");
    assertThat(after.getColorSource()).isEqualTo("USER_INPUT");
  }
}
