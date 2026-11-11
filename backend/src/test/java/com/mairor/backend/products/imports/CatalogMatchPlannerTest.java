package com.mairor.backend.products.imports;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.products.entity.ColorSource;
import com.mairor.backend.products.entity.NameSource;
import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.entity.ProductCategory;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductShadeColor;
import com.mairor.backend.products.entity.ProductType;
import com.mairor.backend.products.entity.ReviewStatus;
import com.mairor.backend.products.imports.ColorReplacementPolicy.Decision;
import com.mairor.backend.products.imports.ImportPlan.Outcome;
import com.mairor.backend.products.imports.ImportPlan.ShadePlan;
import com.mairor.backend.products.imports.ImportPlan.ShadePlan.Action;
import com.mairor.backend.products.imports.SlotMatcher.Kind;
import jakarta.persistence.EntityManager;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.function.Consumer;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

/**
 * 수집 상품 한 건을 DB 에 어떻게 반영할지 계획하는 흐름. 공유 샘플({@code etude_option_image.json})을 고쳐서 쓴다. 이 테스트의 설정은 사진
 * 색의 품질 임계값을 0.8 로 정한 상태다(기본값은 아무 색도 통과시키지 않는다).
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest(
    properties = {
      "spring.jpa.hibernate.ddl-auto=validate",
      "spring.sql.init.mode=always",
      "spring.sql.init.schema-locations=classpath:db/schema/users.sql,classpath:db/schema/products.sql,classpath:db/schema/analysis.sql,classpath:db/schema/pouch.sql,classpath:db/schema/camera.sql",
      "app.security.allowed-origins=http://localhost:3000",
      "catalog.color.min-quality.PRODUCT_PHOTO=0.8",
      "catalog.color.source-value-sites=OFFICIAL:etude.com"
    })
@Transactional
class CatalogMatchPlannerTest {

  private static final Path SAMPLE =
      Path.of("..", "shared", "catalog-import", "samples", "etude_option_image.json");
  private static final ObjectMapper MAPPER = new ObjectMapper();
  private static final String SOURCE = "OFFICIAL:etude.com";
  private static final String PRODUCT_ID = "example-curl-fix-mascara";
  private static final Instant COLLECTED = Instant.parse("2026-11-05T01:32:00Z");

  @Autowired private CatalogMatchPlanner planner;
  @Autowired private EntityManager em;

  private ProductType mascara;
  private ProductType eyeliner;

  @BeforeEach
  void setUp() {
    ProductCategory eye = new ProductCategory("EYE", "아이", true, true, 3);
    em.persist(eye);
    mascara = new ProductType("MASCARA", eye, "마스카라", 2);
    eyeliner = new ProductType("EYELINER", eye, "아이라이너", 3);
    em.persist(mascara);
    em.persist(eyeliner);
    em.flush();
  }

  private CollectedProduct item(Consumer<ObjectNode> change) throws Exception {
    ObjectNode node = (ObjectNode) MAPPER.readTree(Files.readString(SAMPLE));
    change.accept(node);
    var result = CollectedProductReader.read(node);
    assertThat(result.issues()).isEmpty();
    return result.product();
  }

  private static ObjectNode shadeNode(ObjectNode product, int index) {
    return (ObjectNode) product.path("shades").get(index);
  }

  private static ObjectNode colorNode(ObjectNode product, int shadeIndex) {
    return (ObjectNode) shadeNode(product, shadeIndex).path("colors").get(0);
  }

  /** 같은 출처·상품 번호로 이미 저장된 제품. 호수 "01 블랙"(옵션 01-black)은 이름 없는 칸 1개와 색을 가진다. */
  private Product existingProduct(Instant collectedAt) {
    Product product = new Product(mascara, "에뛰드", "예시 컬 픽스 마스카라");
    product.recordSource(SOURCE, PRODUCT_ID, "https://www.etude.com/x", collectedAt);
    ProductShade black = product.addShade("01 블랙", 1, null);
    black.changeSourceOptionId("01-black");
    black
        .addColor(1, null, NameSource.NONE)
        .assignColor(
            ColorSource.PRODUCT_PHOTO, "#1E1B1C", true, ReviewStatus.AUTO_APPROVED, collectedAt);
    em.persist(product);
    em.flush();
    em.clear();
    return product;
  }

  // --- 제품 판정 ---

  @Test
  void aTypeThatCannotBeDecidedIsUnclassified() throws Exception {
    ImportPlan plan =
        planner.plan(
            item(
                n -> {
                  n.put("typeHint", "NO_SUCH_TYPE");
                  n.remove("categoryHint");
                }));

    assertThat(plan.outcome()).isEqualTo(Outcome.UNCLASSIFIED);
    assertThat(plan.type()).isNull();
    assertThat(plan.shades()).isEmpty();
  }

  @Test
  void anUnknownProductIsNewWithItsBadgeRemovedFromTheName() throws Exception {
    ImportPlan plan = planner.plan(item(n -> n.put("name", "[NEW] 예시 컬 픽스 마스카라")));

    assertThat(plan.outcome()).isEqualTo(Outcome.NEW);
    assertThat(plan.existing()).isNull();
    assertThat(plan.cleanedName()).isEqualTo("예시 컬 픽스 마스카라");
    assertThat(plan.type().typeCode()).isEqualTo("MASCARA");
    assertThat(plan.type().categoryCode()).isEqualTo("EYE");
  }

  @Test
  void newProductCreatesEveryShadeAndSlotAndJudgesTheColorsWithTheCurrentThresholds()
      throws Exception {
    ImportPlan plan = planner.plan(item(n -> {}));

    assertThat(plan.shades())
        .hasSize(2)
        .allSatisfy(s -> assertThat(s.action()).isEqualTo(Action.CREATE));
    ShadePlan black = plan.shades().get(0);
    assertThat(black.shade().sourceOptionId()).isEqualTo("01-black");
    assertThat(black.newPrimaryOptionId()).isEqualTo("01-black");
    assertThat(black.slots().kind()).isEqualTo(Kind.CREATE);
    var step = black.slots().steps().get(0);
    assertThat(step.existing()).isNull();
    // 품질 0.93 >= 0.8, 연결 근거 OPTION_IMAGE
    assertThat(step.color().decision()).isEqualTo(Decision.ADOPT);
    assertThat(step.color().status()).isEqualTo(ReviewStatus.AUTO_APPROVED);
    assertThat(plan.isPartial()).isFalse();
  }

  @Test
  void photoColorBelowTheThresholdIsKeptButMarkedBelowThreshold() throws Exception {
    ImportPlan plan = planner.plan(item(n -> colorNode(n, 0).put("colorQuality", 0.5)));

    assertThat(plan.shades().get(0).slots().steps().get(0).color().status())
        .isEqualTo(ReviewStatus.BELOW_THRESHOLD);
    assertThat(plan.shades().get(1).slots().steps().get(0).color().status())
        .isEqualTo(ReviewStatus.AUTO_APPROVED);
  }

  @Test
  void aProductWithTheSameSourceAndNumberIsUpdatedNotDuplicated() throws Exception {
    Product stored = existingProduct(Instant.parse("2026-11-01T00:00:00Z"));

    ImportPlan plan = planner.plan(item(n -> {}));

    assertThat(plan.outcome()).isEqualTo(Outcome.UPDATE);
    assertThat(plan.existing().getId()).isEqualTo(stored.getId());
    ShadePlan black = plan.shades().get(0);
    assertThat(black.action()).isEqualTo(Action.UPDATE);
    assertThat(black.existing().getSourceOptionId()).isEqualTo("01-black");
    // 같은 색이라 바뀌는 것이 없다
    assertThat(black.slots().kind()).isEqualTo(Kind.MATCHED);
    assertThat(black.slots().steps().get(0).color().decision()).isEqualTo(Decision.UNCHANGED);
    // 02 브라운은 새 호수다
    assertThat(plan.shades().get(1).action()).isEqualTo(Action.CREATE);
  }

  @Test
  void anOlderCollectionThanTheStoredProductIsStale() throws Exception {
    existingProduct(Instant.parse("2026-12-01T00:00:00Z"));

    ImportPlan plan = planner.plan(item(n -> {}));

    assertThat(plan.outcome()).isEqualTo(Outcome.STALE);
    assertThat(plan.shades()).isEmpty();
  }

  @Test
  void theSameBrandAndNameFromAnotherSourceIsAmbiguousAndNeverMergedAutomatically()
      throws Exception {
    Product other = new Product(mascara, "에뛰드", "예시 컬 픽스 마스카라");
    em.persist(other);
    em.flush();
    em.clear();

    // 판매 배지를 지운 이름이 같으면 같은 제품 후보다. 출처가 없는 기존 제품과도 합치지 않는다
    ImportPlan plan = planner.plan(item(n -> n.put("name", "[BEST] 예시 컬 픽스 마스카라")));

    assertThat(plan.outcome()).isEqualTo(Outcome.AMBIGUOUS);
    assertThat(plan.existing().getId()).isEqualTo(other.getId());
    assertThat(plan.shades()).isEmpty();
  }

  @Test
  void aChangedTypeIsReportedAndTheExistingTypeIsKept() throws Exception {
    Product product = new Product(eyeliner, "에뛰드", "예시 컬 픽스 마스카라");
    product.recordSource(
        SOURCE, PRODUCT_ID, "https://www.etude.com/x", Instant.parse("2026-11-01T00:00:00Z"));
    em.persist(product);
    em.flush();
    em.clear();

    ImportPlan plan = planner.plan(item(n -> {}));

    assertThat(plan.outcome()).isEqualTo(Outcome.UPDATE);
    assertThat(plan.reasons()).containsExactly(ImportReason.TYPE_KEPT);
    assertThat(plan.isPartial()).isTrue();
  }

  // --- 호수·색 ---

  @Test
  void aSeedShadeWithTheSameNameButNoOptionIdIsHeldNotLinked() throws Exception {
    Product product = new Product(mascara, "에뛰드", "예시 컬 픽스 마스카라");
    product.recordSource(
        SOURCE, PRODUCT_ID, "https://www.etude.com/x", Instant.parse("2026-11-01T00:00:00Z"));
    product.addShade("01 블랙", 1, null);
    em.persist(product);
    em.flush();
    em.clear();

    ImportPlan plan = planner.plan(item(n -> {}));

    ShadePlan black = plan.shades().get(0);
    assertThat(black.action()).isEqualTo(Action.HELD);
    assertThat(black.reasons()).containsExactly(ImportReason.SHADE_AMBIGUOUS);
    assertThat(black.slots()).isNull();
    assertThat(plan.shades().get(1).action()).isEqualTo(Action.CREATE);
    assertThat(plan.isPartial()).isTrue();
  }

  @Test
  void anOperatorCorrectedColorIsKeptAndTheItemIsPartial() throws Exception {
    existingProduct(Instant.parse("2026-11-01T00:00:00Z"));
    var stored =
        em.createQuery("select c from ProductShadeColor c", ProductShadeColor.class)
            .getSingleResult();
    stored.changeReviewStatus(ReviewStatus.APPROVED);
    em.flush();
    em.clear();

    ImportPlan plan = planner.plan(item(n -> colorNode(n, 0).put("hex", "#222222")));

    var step = plan.shades().get(0).slots().steps().get(0);
    assertThat(step.color().decision()).isEqualTo(Decision.KEPT_OPERATOR);
    assertThat(plan.allReasons()).contains(ImportReason.COLOR_KEPT_OPERATOR);
    assertThat(plan.isPartial()).isTrue();
  }

  @Test
  void aColorReplacedByTheNewCollectionIsNotAPartialResult() throws Exception {
    Product product = new Product(mascara, "에뛰드", "예시 컬 픽스 마스카라");
    product.recordSource(
        SOURCE, PRODUCT_ID, "https://www.etude.com/x", Instant.parse("2026-11-01T00:00:00Z"));
    ProductShade black = product.addShade("01 블랙", 1, null);
    black.changeSourceOptionId("01-black");
    // 웹 사진에서 얻은 색(우선순위 낮음)이 있고 칸에 이름이 있다
    black
        .addColor(1, "Black", NameSource.SITE_TEXT)
        .assignColor(
            ColorSource.WEB_PHOTO,
            "#101010",
            true,
            ReviewStatus.AUTO_APPROVED,
            Instant.parse("2026-11-01T00:00:00Z"));
    em.persist(product);
    em.flush();
    em.clear();

    ImportPlan plan =
        planner.plan(
            item(
                n -> {
                  colorNode(n, 0).put("name", "Black");
                  colorNode(n, 0).put("nameSource", "SITE_TEXT");
                }));

    var step = plan.shades().get(0).slots().steps().get(0);
    assertThat(step.color().decision()).isEqualTo(Decision.REPLACE);
    assertThat(plan.allReasons()).containsExactly(ImportReason.COLOR_REPLACED);
    assertThat(plan.isPartial()).isFalse();
  }

  @Test
  void aShadeWhoseSlotsCannotBeMatchedKeepsItsExistingSlots() throws Exception {
    Product product = new Product(mascara, "에뛰드", "예시 컬 픽스 마스카라");
    product.recordSource(
        SOURCE, PRODUCT_ID, "https://www.etude.com/x", Instant.parse("2026-11-01T00:00:00Z"));
    ProductShade black = product.addShade("01 블랙", 1, null);
    black.changeSourceOptionId("01-black");
    black
        .addColor(1, null, NameSource.NONE)
        .assignColor(
            ColorSource.PRODUCT_PHOTO,
            "#1E1B1C",
            true,
            ReviewStatus.AUTO_APPROVED,
            Instant.parse("2026-11-01T00:00:00Z"));
    black
        .addColor(2, null, NameSource.NONE)
        .assignColor(
            ColorSource.PRODUCT_PHOTO,
            "#4A3427",
            true,
            ReviewStatus.AUTO_APPROVED,
            Instant.parse("2026-11-01T00:00:00Z"));
    em.persist(product);
    em.flush();
    em.clear();

    // 칸 수·격자는 같지만 한 칸의 색이 크게 달라졌다
    ImportPlan plan =
        planner.plan(
            item(
                n -> {
                  addSecondColor(n, "#4A3427");
                  colorNode(n, 0).put("hex", "#E8452C");
                }));

    ShadePlan blackPlan = plan.shades().get(0);
    assertThat(blackPlan.slots().kind()).isEqualTo(Kind.KEPT);
    assertThat(blackPlan.reasons()).containsExactly(ImportReason.SHADE_LAYOUT_CHANGED);
    assertThat(plan.isPartial()).isTrue();
  }

  private static void addSecondColor(ObjectNode product, String hex) {
    ObjectNode first = colorNode(product, 0);
    ObjectNode second = first.deepCopy();
    second.put("sortOrder", 2);
    second.put("hex", hex);
    second.put("evidenceKey", PRODUCT_ID + "/01-black/2");
    ((tools.jackson.databind.node.ArrayNode) shadeNode(product, 0).path("colors")).add(second);
  }

  // --- 갱신 판정 경계 조건(코드 리뷰 반영) ---

  @Test
  void optionsThatWereMergedBeforeAndSplitNowDoNotBothUpdateTheSameShade() throws Exception {
    Product product = new Product(mascara, "에뛰드", "예시 컬 픽스 마스카라");
    product.recordSource(
        SOURCE, PRODUCT_ID, "https://www.etude.com/x", Instant.parse("2026-11-01T00:00:00Z"));
    ProductShade black = product.addShade("01 블랙", 1, null);
    black.changeSourceOptionId("A");
    black.addOptionAlias("B");
    em.persist(product);
    em.flush();
    em.clear();

    // 이전에는 A·B 를 한 호수로 합쳤는데, 이번에는 용량이 달라 합치지 않는다
    ImportPlan plan =
        planner.plan(
            item(
                n -> {
                  ObjectNode first = shadeNode(n, 0);
                  first.put("sourceOptionId", "A");
                  first.put("name", "01 블랙");
                  ((ObjectNode) first.path("variantHints")).put("volume", "3g");
                  ((ObjectNode) first.path("colors").get(0))
                      .put("evidenceKey", PRODUCT_ID + "/A/1");
                  ObjectNode second = shadeNode(n, 1);
                  second.put("sourceOptionId", "B");
                  second.put("name", "[NEW] 01 블랙");
                  ((ObjectNode) second.path("variantHints")).put("volume", "5g");
                  ((ObjectNode) second.path("colors").get(0))
                      .put("evidenceKey", PRODUCT_ID + "/B/1");
                }));

    assertThat(plan.shades()).hasSize(2);
    assertThat(plan.shades())
        .allSatisfy(
            shade -> {
              assertThat(shade.action()).isEqualTo(Action.HELD);
              assertThat(shade.existing()).isNull();
              assertThat(shade.reasons())
                  .contains(ImportReason.SHADE_AMBIGUOUS, ImportReason.SHADE_MERGE_HELD);
            });
    assertThat(plan.isPartial()).isTrue();
  }

  @Test
  void renamingAProductOntoAnotherProductsNameIsHeld() throws Exception {
    Product stored = new Product(mascara, "에뛰드", "예시 컬 픽스 마스카라");
    stored.recordSource(
        SOURCE, PRODUCT_ID, "https://www.etude.com/x", Instant.parse("2026-11-01T00:00:00Z"));
    Product other = new Product(mascara, "에뛰드", "새 이름 마스카라");
    em.persist(stored);
    em.persist(other);
    em.flush();
    em.clear();

    // 같은 출처·상품 번호라 원래는 갱신이지만, 새 이름이 같은 종류의 다른 제품 이름과 같다
    ImportPlan plan = planner.plan(item(n -> n.put("name", "[NEW] 새 이름 마스카라")));

    assertThat(plan.outcome()).isEqualTo(Outcome.AMBIGUOUS);
    assertThat(plan.existing().getId()).isEqualTo(other.getId());
    assertThat(plan.reasons()).containsExactly(ImportReason.PRODUCT_NAME_CONFLICT);
    assertThat(plan.shades()).isEmpty();
    assertThat(plan.isPartial()).isTrue();
  }

  @Test
  void renamingAProductToANameNobodyElseHasIsAnUpdate() throws Exception {
    Product stored = new Product(mascara, "에뛰드", "예시 컬 픽스 마스카라");
    stored.recordSource(
        SOURCE, PRODUCT_ID, "https://www.etude.com/x", Instant.parse("2026-11-01T00:00:00Z"));
    em.persist(stored);
    em.flush();
    em.clear();

    ImportPlan plan = planner.plan(item(n -> n.put("name", "완전히 새 이름")));

    assertThat(plan.outcome()).isEqualTo(Outcome.UPDATE);
    assertThat(plan.cleanedName()).isEqualTo("완전히 새 이름");
  }

  @Test
  void aColorFromAnAllowedSiteValueReplacesThePhotoColorOfASingleSlot() throws Exception {
    existingProduct(Instant.parse("2026-11-01T00:00:00Z"));

    // 같은 옵션의 단일 칸에 사이트가 준 색값이 왔다. 사진 색과 크게 달라도 같은 colorId 로 색만 바꾼다
    ImportPlan plan =
        planner.plan(
            item(
                n -> {
                  ObjectNode color = colorNode(n, 0);
                  color.put("hex", "#E8452C");
                  color.put("colorSource", "SOURCE_VALUE");
                  color.putNull("colorQuality");
                }));

    ShadePlan blackPlan = plan.shades().get(0);
    assertThat(blackPlan.slots().kind()).isEqualTo(Kind.MATCHED);
    var step = blackPlan.slots().steps().get(0);
    assertThat(step.existing()).isNotNull();
    assertThat(step.color().decision()).isEqualTo(Decision.REPLACE);
    assertThat(plan.allReasons()).containsExactly(ImportReason.COLOR_REPLACED);
    assertThat(plan.isPartial()).isFalse();
  }

  @Test
  void aColorFromASourceThatIsNoLongerAllowedIsDowngradedWithoutCountingAsPartial()
      throws Exception {
    Product product = new Product(mascara, "에뛰드", "예시 컬 픽스 마스카라");
    product.recordSource(
        SOURCE, PRODUCT_ID, "https://www.etude.com/x", Instant.parse("2026-11-01T00:00:00Z"));
    ProductShade black = product.addShade("01 블랙", 1, null);
    black.changeSourceOptionId("01-black");
    // 모델 추정 색은 기본 설정에서 쓸 수 없는 출처다
    black
        .addColor(1, null, NameSource.NONE)
        .assignColor(
            ColorSource.LLM_ESTIMATE,
            "#1E1B1C",
            true,
            ReviewStatus.AUTO_APPROVED,
            Instant.parse("2026-11-01T00:00:00Z"));
    em.persist(product);
    em.flush();
    em.clear();

    ImportPlan plan =
        planner.plan(
            item(
                n -> {
                  ObjectNode color = colorNode(n, 0);
                  color.put("colorSource", "LLM_ESTIMATE");
                  color.putNull("colorQuality");
                }));

    var step = plan.shades().get(0).slots().steps().get(0);
    assertThat(step.color().status()).isEqualTo(ReviewStatus.BELOW_THRESHOLD);
    assertThat(plan.allReasons()).contains(ImportReason.COLOR_DOWNGRADED);
    assertThat(plan.isPartial()).isFalse();
  }

  @Test
  void planningDoesNotWriteToTheDatabase() throws Exception {
    existingProduct(Instant.parse("2026-11-01T00:00:00Z"));
    long productsBefore = count("Product");
    long shadesBefore = count("ProductShade");
    long colorsBefore = count("ProductShadeColor");

    planner.plan(item(n -> colorNode(n, 0).put("hex", "#E8452C")));
    em.flush();

    assertThat(count("Product")).isEqualTo(productsBefore);
    assertThat(count("ProductShade")).isEqualTo(shadesBefore);
    assertThat(count("ProductShadeColor")).isEqualTo(colorsBefore);
  }

  private long count(String entity) {
    return em.createQuery("select count(e) from " + entity + " e", Long.class).getSingleResult();
  }

  // --- 기존 색 재판정은 새 칸 대응과 분리한다(코드 리뷰 반영) ---

  /** 호수 "01 블랙"에 이름 없는 칸 둘을 가진 기존 제품. */
  private Product storeTwoSlotProduct(
      ColorSource firstSource,
      ReviewStatus firstStatus,
      ColorSource secondSource,
      ReviewStatus secondStatus) {
    Instant at = Instant.parse("2026-11-01T00:00:00Z");
    Product product = new Product(mascara, "에뛰드", "예시 컬 픽스 마스카라");
    product.recordSource(SOURCE, PRODUCT_ID, "https://www.etude.com/x", at);
    ProductShade black = product.addShade("01 블랙", 1, null);
    black.changeSourceOptionId("01-black");
    black
        .addColor(1, null, NameSource.NONE)
        .assignColor(firstSource, "#1E1B1C", true, firstStatus, at);
    black
        .addColor(2, null, NameSource.NONE)
        .assignColor(secondSource, "#4A3427", true, secondStatus, at);
    em.persist(product);
    em.flush();
    em.clear();
    return product;
  }

  private static void makeShadeNotFound(ObjectNode product) {
    ObjectNode shade = shadeNode(product, 0);
    shade.put("colorStatus", "NOT_FOUND");
    ((tools.jackson.databind.node.ArrayNode) shade.path("colors")).removeAll();
  }

  @Test
  void aForbiddenSourceColorIsDowngradedEvenWhenTheNewCollectionHasNoSlots() throws Exception {
    storeTwoSlotProduct(
        ColorSource.LLM_ESTIMATE,
        ReviewStatus.AUTO_APPROVED,
        ColorSource.PRODUCT_PHOTO,
        ReviewStatus.AUTO_APPROVED);

    // 재수집이 NOT_FOUND 라 새 칸이 하나도 없다. 칸 대응은 할 일이 없지만 금지된 출처의 색은 중단한다
    ImportPlan plan = planner.plan(item(CatalogMatchPlannerTest::makeShadeNotFound));

    ImportPlan.SlotPlan slots = plan.shades().get(0).slots();
    assertThat(slots.kind()).isEqualTo(Kind.NONE);
    assertThat(slots.steps()).isEmpty();
    assertThat(slots.downgrades()).hasSize(1);
    assertThat(slots.downgrades().get(0).getColorSource()).isEqualTo(ColorSource.LLM_ESTIMATE);
    assertThat(plan.allReasons()).containsExactly(ImportReason.COLOR_DOWNGRADED);
    // 정책을 따른 정상 반영이라 부분 반영이 아니다
    assertThat(plan.isPartial()).isFalse();
  }

  @Test
  void aForbiddenSourceColorIsDowngradedEvenWhenTheSlotLayoutIsKept() throws Exception {
    storeTwoSlotProduct(
        ColorSource.LLM_ESTIMATE,
        ReviewStatus.AUTO_APPROVED,
        ColorSource.PRODUCT_PHOTO,
        ReviewStatus.AUTO_APPROVED);

    // 칸 수·격자는 같지만 첫 칸의 색이 크게 달라 대응을 믿을 수 없다 -> 기존 칸 배치를 지킨다
    ImportPlan plan =
        planner.plan(
            item(
                n -> {
                  addSecondColor(n, "#4A3427");
                  colorNode(n, 0).put("hex", "#E8452C");
                }));

    ImportPlan.SlotPlan slots = plan.shades().get(0).slots();
    assertThat(slots.kind()).isEqualTo(Kind.KEPT);
    assertThat(slots.steps()).isEmpty();
    assertThat(slots.downgrades()).hasSize(1);
    assertThat(slots.downgrades().get(0).getColorSource()).isEqualTo(ColorSource.LLM_ESTIMATE);
    assertThat(plan.allReasons())
        .containsExactlyInAnyOrder(
            ImportReason.SHADE_LAYOUT_CHANGED, ImportReason.COLOR_DOWNGRADED);
  }

  @Test
  void operatorCorrectedAndAlreadyUnusableColorsAreNotTouchedByTheStandaloneCheck()
      throws Exception {
    storeTwoSlotProduct(
        ColorSource.LLM_ESTIMATE,
        ReviewStatus.APPROVED,
        ColorSource.LLM_ESTIMATE,
        ReviewStatus.BELOW_THRESHOLD);

    ImportPlan plan = planner.plan(item(CatalogMatchPlannerTest::makeShadeNotFound));

    assertThat(plan.shades().get(0).slots().downgrades()).isEmpty();
    assertThat(plan.allReasons()).isEmpty();
  }

  @Test
  void anAllowedSourceColorIsNotDowngradedWhenTheNewCollectionHasNoSlots() throws Exception {
    storeTwoSlotProduct(
        ColorSource.PRODUCT_PHOTO,
        ReviewStatus.AUTO_APPROVED,
        ColorSource.SWATCH_CHIP,
        ReviewStatus.AUTO_APPROVED);

    ImportPlan plan = planner.plan(item(CatalogMatchPlannerTest::makeShadeNotFound));

    assertThat(plan.shades().get(0).slots().downgrades()).isEmpty();
    assertThat(plan.allReasons()).isEmpty();
  }

  @Test
  void theSameHexFromAnotherPhotoWithWeakEvidenceDoesNotLowerTheExistingColor() throws Exception {
    existingProduct(Instant.parse("2026-11-01T00:00:00Z"));

    // 기존과 같은 #1E1B1C 이지만 다른 사진에서 나왔고 품질이 기준(0.8) 미달이다
    ImportPlan plan = planner.plan(item(n -> colorNode(n, 0).put("colorQuality", 0.5)));

    var step = plan.shades().get(0).slots().steps().get(0);
    assertThat(step.color().decision()).isEqualTo(Decision.UNCHANGED);
    assertThat(step.color().status()).isEqualTo(ReviewStatus.AUTO_APPROVED);
    assertThat(plan.shades().get(0).slots().downgrades()).isEmpty();
    assertThat(plan.allReasons()).isEmpty();
  }

  // --- 갱신 중인 제품의 기존 호수 전체에 출처 금지 적용(코드 리뷰 반영) ---

  /** 호수 "01 블랙"(옵션 있음)과, 이번 수집에 없는 호수 "03 모카"를 가진 기존 제품. */
  private Product storeProductWithAShadeMissingFromTheCollection(
      ColorSource mochaSource, ReviewStatus mochaStatus) {
    Instant at = Instant.parse("2026-11-01T00:00:00Z");
    Product product = new Product(mascara, "에뛰드", "예시 컬 픽스 마스카라");
    product.recordSource(SOURCE, PRODUCT_ID, "https://www.etude.com/x", at);
    ProductShade black = product.addShade("01 블랙", 1, null);
    black.changeSourceOptionId("01-black");
    black
        .addColor(1, null, NameSource.NONE)
        .assignColor(ColorSource.PRODUCT_PHOTO, "#1E1B1C", true, ReviewStatus.AUTO_APPROVED, at);
    ProductShade mocha = product.addShade("03 모카", 3, null);
    mocha.changeSourceOptionId("03-mocha");
    mocha
        .addColor(1, null, NameSource.NONE)
        .assignColor(mochaSource, "#6B4F3A", true, mochaStatus, at);
    em.persist(product);
    em.flush();
    em.clear();
    return product;
  }

  @Test
  void aForbiddenSourceColorOfAShadeMissingFromTheNewCollectionIsDowngraded() throws Exception {
    storeProductWithAShadeMissingFromTheCollection(
        ColorSource.LLM_ESTIMATE, ReviewStatus.AUTO_APPROVED);

    // 재수집에는 01·02 호수만 있고 03 모카는 없다. 모카의 모델 추정 색은 기본 설정에서 쓸 수 없는 출처다
    ImportPlan plan = planner.plan(item(n -> {}));

    assertThat(plan.outcome()).isEqualTo(Outcome.UPDATE);
    assertThat(plan.downgrades()).hasSize(1);
    assertThat(plan.downgrades().get(0).getColorSource()).isEqualTo(ColorSource.LLM_ESTIMATE);
    assertThat(plan.downgrades().get(0).getShade().getName()).isEqualTo("03 모카");
    assertThat(plan.allReasons()).containsExactly(ImportReason.COLOR_DOWNGRADED);
    // 정책을 따른 정상 반영이라 부분 반영이 아니다
    assertThat(plan.isPartial()).isFalse();
  }

  @Test
  void aForbiddenSourceColorOfAHeldShadeIsStillDowngraded() throws Exception {
    Instant at = Instant.parse("2026-11-01T00:00:00Z");
    Product product = new Product(mascara, "에뛰드", "예시 컬 픽스 마스카라");
    product.recordSource(SOURCE, PRODUCT_ID, "https://www.etude.com/x", at);
    // 옵션 값이 없는 시드 호수. 같은 이름이라 새 수집과 같은 호수인지 알 수 없어 보류된다
    ProductShade seed = product.addShade("01 블랙", 1, null);
    seed.addColor(1, null, NameSource.NONE)
        .assignColor(ColorSource.LLM_ESTIMATE, "#1E1B1C", true, ReviewStatus.AUTO_APPROVED, at);
    em.persist(product);
    em.flush();
    em.clear();

    ImportPlan plan = planner.plan(item(n -> {}));

    assertThat(plan.shades().get(0).action()).isEqualTo(Action.HELD);
    assertThat(plan.downgrades()).hasSize(1);
    assertThat(plan.allReasons())
        .containsExactlyInAnyOrder(ImportReason.SHADE_AMBIGUOUS, ImportReason.COLOR_DOWNGRADED);
    assertThat(plan.isPartial()).isTrue();
  }

  @Test
  void slotsHandledByAShadePlanAreNotReportedAgainAtTheProductLevel() throws Exception {
    storeTwoSlotProduct(
        ColorSource.LLM_ESTIMATE,
        ReviewStatus.AUTO_APPROVED,
        ColorSource.PRODUCT_PHOTO,
        ReviewStatus.AUTO_APPROVED);

    ImportPlan plan = planner.plan(item(CatalogMatchPlannerTest::makeShadeNotFound));

    assertThat(plan.shades().get(0).slots().downgrades()).hasSize(1);
    assertThat(plan.downgrades()).isEmpty();
  }

  @Test
  void operatorAllowedAndUnusableColorsOfAMissingShadeAreLeftAlone() throws Exception {
    storeProductWithAShadeMissingFromTheCollection(ColorSource.LLM_ESTIMATE, ReviewStatus.APPROVED);
    assertThat(planner.plan(item(n -> {})).downgrades()).isEmpty();
  }

  @Test
  void anAllowedSourceColorOfAMissingShadeIsLeftAlone() throws Exception {
    storeProductWithAShadeMissingFromTheCollection(
        ColorSource.WEB_PHOTO, ReviewStatus.AUTO_APPROVED);

    ImportPlan plan = planner.plan(item(n -> {}));

    assertThat(plan.downgrades()).isEmpty();
    assertThat(plan.allReasons()).isEmpty();
  }

  @Test
  void aNewProductHasNothingToDowngrade() throws Exception {
    assertThat(planner.plan(item(n -> {})).downgrades()).isEmpty();
  }
}
