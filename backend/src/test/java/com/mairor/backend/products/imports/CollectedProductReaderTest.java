package com.mairor.backend.products.imports;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.products.entity.ColorSource;
import com.mairor.backend.products.entity.NameSource;
import com.mairor.backend.products.entity.SaleStatus;
import com.mairor.backend.products.imports.CollectedProduct.CollectedColor;
import com.mairor.backend.products.imports.CollectedProduct.CollectedShade;
import com.mairor.backend.products.imports.CollectedProduct.ColorStatus;
import com.mairor.backend.products.imports.CollectedProduct.ShadeLink;
import com.mairor.backend.products.imports.CollectedProduct.SlotOrderBasis;
import com.mairor.backend.products.imports.CollectedProductReader.ReadResult;
import com.mairor.backend.products.imports.ImportIssue.Code;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.function.Consumer;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/**
 * 수집 상품 한 건을 읽는 규칙. 공유 샘플({@code shared/catalog-import/samples/})을 그대로 읽어, 수집기와 적재 쪽이 같은 계약을 본다는 것을
 * 확인한다. 나머지는 정상 샘플의 한 곳만 고쳐서 문제가 정확히 그 곳에서만 나는지 본다.
 */
class CollectedProductReaderTest {

  private static final Path SAMPLES = Path.of("..", "shared", "catalog-import", "samples");
  private static final ObjectMapper MAPPER = new ObjectMapper();

  private static ObjectNode sample(String file) throws Exception {
    return (ObjectNode) MAPPER.readTree(Files.readString(SAMPLES.resolve(file)));
  }

  /** 정상 샘플을 고쳐서 읽는다. */
  private static ReadResult readChanged(Consumer<ObjectNode> change) throws Exception {
    ObjectNode node = sample("etude_option_image.json");
    change.accept(node);
    return CollectedProductReader.read(node);
  }

  private static ObjectNode firstShade(ObjectNode product) {
    return (ObjectNode) product.path("shades").get(0);
  }

  private static ObjectNode firstColor(ObjectNode product) {
    return (ObjectNode) firstShade(product).path("colors").get(0);
  }

  private static List<String> paths(ReadResult result) {
    return result.issues().stream().map(ImportIssue::path).toList();
  }

  private static void assertSingleIssue(ReadResult result, String path, Code code) {
    assertThat(result.product()).isNull();
    assertThat(result.issues()).hasSize(1);
    assertThat(result.issues().get(0).path()).isEqualTo(path);
    assertThat(result.issues().get(0).code()).isEqualTo(code);
  }

  // --- 공유 샘플 ---

  @Test
  void validSamplesAreAccepted() throws Exception {
    for (String file :
        List.of(
            "romand_single_unverified.json",
            "romand_duo_shade.json",
            "etude_option_image.json",
            "romand_named_palette.json")) {
      ReadResult result = CollectedProductReader.read(sample(file));

      assertThat(result.issues()).as(file).isEmpty();
      assertThat(result.product()).as(file).isNotNull();
    }
  }

  @Test
  void brokenSampleIsRejectedOnlyForItsTwoDefects() throws Exception {
    ReadResult result = CollectedProductReader.read(sample("invalid_incomplete_source.json"));

    assertThat(result.product()).isNull();
    assertThat(result.itemKey()).isEqualTo("000004");
    assertThat(result.issues())
        .extracting(ImportIssue::path, ImportIssue::code)
        .containsExactlyInAnyOrder(
            org.assertj.core.groups.Tuple.tuple("sourceProductId", Code.REQUIRED),
            org.assertj.core.groups.Tuple.tuple("shades[0].colors[0].hex", Code.INVALID_FORMAT));
  }

  @Test
  void singleColorSampleIsReadWithEveryField() throws Exception {
    CollectedProduct product =
        CollectedProductReader.read(sample("etude_option_image.json")).product();

    assertThat(product.contractVersion()).isEqualTo(1);
    assertThat(product.itemKey()).isEqualTo("000003");
    assertThat(product.source()).isEqualTo("OFFICIAL:etude.com");
    assertThat(product.sourceProductId()).isEqualTo("example-curl-fix-mascara");
    assertThat(product.sourceLanguage()).isEqualTo("ko");
    assertThat(product.collectedAt().toInstant().toString()).isEqualTo("2026-11-05T01:32:00Z");
    assertThat(product.brand()).isEqualTo("에뛰드");
    assertThat(product.sourceCategoryPath()).containsExactly("eye");
    assertThat(product.categoryHint()).isEqualTo("EYE");
    assertThat(product.typeHint()).isEqualTo("MASCARA");
    assertThat(product.saleStatus()).isEqualTo(SaleStatus.ON_SALE);
    assertThat(product.shades()).hasSize(2);
    CollectedShade shade = product.shades().get(0);
    assertThat(shade.sourceOptionId()).isEqualTo("01-black");
    assertThat(shade.name()).isEqualTo("01 블랙");
    assertThat(shade.slotOrderBasis()).isEqualTo(SlotOrderBasis.GRID);
    assertThat(shade.colorStatus()).isEqualTo(ColorStatus.EXTRACTED);
    assertThat(shade.hasVariantHints()).isTrue();
    assertThat(shade.variantHints().volume()).isNull();
    CollectedColor color = shade.colors().get(0);
    assertThat(color.hex()).isEqualTo("#1E1B1C");
    assertThat(color.colorSource()).isEqualTo(ColorSource.PRODUCT_PHOTO);
    assertThat(color.shadeLink()).isEqualTo(ShadeLink.OPTION_IMAGE);
    assertThat(color.colorQuality()).isEqualTo(0.93);
    assertThat(color.nameSource()).isEqualTo(NameSource.NONE);
    assertThat(color.evidenceKey()).isEqualTo("example-curl-fix-mascara/01-black/1");
  }

  @Test
  void colorlessShadeAndMissingShadeFieldsAreAccepted() throws Exception {
    CollectedProduct product =
        CollectedProductReader.read(sample("romand_single_unverified.json")).product();

    CollectedShade notFound = product.shades().get(1);
    assertThat(notFound.colorStatus()).isEqualTo(ColorStatus.NOT_FOUND);
    assertThat(notFound.colors()).isEmpty();
    assertThat(notFound.slotOrderBasis()).isEqualTo(SlotOrderBasis.UNKNOWN);
  }

  @Test
  void productWithoutShadesAndWithoutOptionalFieldsIsAccepted() throws Exception {
    ReadResult result =
        readChanged(
            n -> {
              n.remove("shades");
              n.remove("imageUrl");
              n.remove("saleStatus");
              n.remove("sourceCategoryPath");
              n.remove("categoryHint");
              n.remove("typeHint");
              n.remove("warnings");
            });

    assertThat(result.issues()).isEmpty();
    assertThat(result.product().shades()).isEmpty();
    assertThat(result.product().sourceCategoryPath()).isEmpty();
    assertThat(result.product().warnings()).isEmpty();
    assertThat(result.product().saleStatus()).isNull();
  }

  @Test
  void unknownFieldsAreIgnored() throws Exception {
    ReadResult result = readChanged(n -> n.put("futureField", "x"));

    assertThat(result.issues()).isEmpty();
  }

  @Test
  void variantHintsAreReadAndMissingHintsStayMissing() throws Exception {
    ReadResult withHints =
        readChanged(
            n -> {
              ObjectNode hints = (ObjectNode) firstShade(n).path("variantHints");
              hints.put("volume", "3.5g");
              hints.put("listPrice", 12000);
              hints.putObject("optionAttributes").put("용량", "본품");
            });
    ReadResult withoutHints = readChanged(n -> firstShade(n).remove("variantHints"));

    var hints = withHints.product().shades().get(0).variantHints();
    assertThat(hints.volume()).isEqualTo("3.5g");
    assertThat(hints.listPrice()).isEqualTo("12000");
    assertThat(hints.optionAttributes()).containsEntry("용량", "본품");
    // 객체가 없으면 '수집하지 않음'이라 없는 채로 둔다. 비어 있는 객체로 바꾸지 않는다
    assertThat(withoutHints.product().shades().get(0).hasVariantHints()).isFalse();
  }

  // --- 계약 판 ---

  @Test
  void unsupportedContractVersionStopsReadingAndKeepsItemKey() throws Exception {
    ReadResult result = readChanged(n -> n.put("contractVersion", 2));

    assertSingleIssue(result, "contractVersion", Code.UNSUPPORTED_CONTRACT_VERSION);
    assertThat(result.itemKey()).isEqualTo("000003");
  }

  @Test
  void missingOrNonIntegerContractVersionIsRejected() throws Exception {
    assertSingleIssue(
        readChanged(n -> n.remove("contractVersion")), "contractVersion", Code.REQUIRED);
    assertSingleIssue(
        readChanged(n -> n.put("contractVersion", "1")), "contractVersion", Code.WRONG_TYPE);
    assertSingleIssue(
        readChanged(n -> n.put("contractVersion", 1.5)), "contractVersion", Code.WRONG_TYPE);
  }

  @Test
  void nonObjectItemIsRejected() {
    ReadResult result = CollectedProductReader.read(MAPPER.createArrayNode());

    assertSingleIssue(result, "$", Code.WRONG_TYPE);
    assertThat(result.itemKey()).isNull();
  }

  // --- 필수 값·형식 ---

  @Test
  void requiredProductFieldsMustBePresentAndNotBlank() throws Exception {
    for (String field :
        List.of(
            "itemKey",
            "source",
            "sourceProductId",
            "sourceUrl",
            "sourceLanguage",
            "collectedAt",
            "brand",
            "name")) {
      assertSingleIssue(readChanged(n -> n.remove(field)), field, Code.REQUIRED);
      assertSingleIssue(readChanged(n -> n.put(field, "   ")), field, Code.REQUIRED);
      assertSingleIssue(readChanged(n -> n.putNull(field)), field, Code.REQUIRED);
    }
  }

  @Test
  void wrongJsonTypesAreRejected() throws Exception {
    assertSingleIssue(readChanged(n -> n.put("brand", 12)), "brand", Code.WRONG_TYPE);
    assertSingleIssue(readChanged(n -> n.put("shades", "x")), "shades", Code.WRONG_TYPE);
    assertSingleIssue(
        readChanged(n -> n.put("sourceCategoryPath", "립")), "sourceCategoryPath", Code.WRONG_TYPE);
    assertSingleIssue(
        readChanged(n -> firstShade(n).put("sortOrder", "1")),
        "shades[0].sortOrder",
        Code.WRONG_TYPE);
  }

  @Test
  void sourceMustBeOfficialOrWebWithADomain() throws Exception {
    assertThat(readChanged(n -> n.put("source", "WEB:shop.example.com")).issues()).isEmpty();
    for (String bad :
        List.of("etude.com", "OFFICIAL:", "OFFICIAL:etude.com/path", "OLIVE:oliveyoung.co.kr")) {
      assertSingleIssue(readChanged(n -> n.put("source", bad)), "source", Code.INVALID_FORMAT);
    }
  }

  @Test
  void longDomainSourceFits() throws Exception {
    // 30자를 넘는 출처(OFFICIAL:www.thesaemcosmetic.com)도 받는다
    ReadResult result = readChanged(n -> n.put("source", "OFFICIAL:www.thesaemcosmetic.com"));

    assertThat(result.issues()).isEmpty();
    assertThat(result.product().source()).hasSize(32);
  }

  @Test
  void urlLanguageAndTimeFormatsAreChecked() throws Exception {
    assertSingleIssue(
        readChanged(n -> n.put("sourceUrl", "ftp://example.com/a")),
        "sourceUrl",
        Code.INVALID_FORMAT);
    assertSingleIssue(
        readChanged(n -> n.put("sourceLanguage", "Korean")), "sourceLanguage", Code.INVALID_FORMAT);
    assertThat(readChanged(n -> n.put("sourceLanguage", "zh-TW")).issues()).isEmpty();
    assertSingleIssue(
        readChanged(n -> n.put("collectedAt", "2026-11-05 10:32:00")),
        "collectedAt",
        Code.INVALID_FORMAT);
    // 시간대가 없는 시각은 받지 않는다
    assertSingleIssue(
        readChanged(n -> n.put("collectedAt", "2026-11-05T10:32:00")),
        "collectedAt",
        Code.INVALID_FORMAT);
  }

  @Test
  void tooLongValuesAreRejectedNotTruncated() throws Exception {
    assertSingleIssue(readChanged(n -> n.put("brand", "b".repeat(101))), "brand", Code.TOO_LONG);
    assertSingleIssue(readChanged(n -> n.put("name", "n".repeat(201))), "name", Code.TOO_LONG);
    assertSingleIssue(
        readChanged(n -> firstShade(n).put("name", "s".repeat(101))),
        "shades[0].name",
        Code.TOO_LONG);
    assertSingleIssue(
        readChanged(n -> n.put("imageUrl", "https://x/" + "a".repeat(1000))),
        "imageUrl",
        Code.TOO_LONG);
  }

  @Test
  void valuesAtTheLimitAreAcceptedAfterTrimmingSurroundingWhitespace() throws Exception {
    ReadResult result =
        readChanged(
            n -> {
              n.put("brand", " " + "b".repeat(100) + " ");
              n.put("name", " " + "n".repeat(200));
            });

    assertThat(result.issues()).isEmpty();
    assertThat(result.product().brand()).hasSize(100);
    assertThat(result.product().name()).hasSize(200);
  }

  @Test
  void saleStatusMustBeKnown() throws Exception {
    assertSingleIssue(
        readChanged(n -> n.put("saleStatus", "ARCHIVED")), "saleStatus", Code.INVALID_VALUE);
  }

  // --- 호수 ---

  @Test
  void sameOptionIdTwiceInOneProductIsRejected() throws Exception {
    ReadResult result =
        readChanged(
            n -> {
              ArrayNode shades = (ArrayNode) n.path("shades");
              ObjectNode second = (ObjectNode) shades.get(1);
              second.put("sourceOptionId", "01-black");
              ((ObjectNode) second.path("colors").get(0))
                  .put("evidenceKey", "example-curl-fix-mascara/01-black/1");
            });

    assertSingleIssue(result, "shades[1].sourceOptionId", Code.DUPLICATE);
  }

  @Test
  void colorStatusMustAgreeWithTheSlots() throws Exception {
    assertSingleIssue(
        readChanged(n -> firstShade(n).put("colorStatus", "NOT_FOUND")),
        "shades[0].colorStatus",
        Code.INCONSISTENT);
    assertSingleIssue(
        readChanged(n -> firstShade(n).put("colorStatus", "BROKEN")),
        "shades[0].colorStatus",
        Code.INVALID_VALUE);
    ReadResult noColors = readChanged(n -> ((ArrayNode) firstShade(n).path("colors")).removeAll());
    assertSingleIssue(noColors, "shades[0].colorStatus", Code.INCONSISTENT);
  }

  @Test
  void slotOrderBasisIsRequiredOnlyWhenThereAreSlots() throws Exception {
    assertSingleIssue(
        readChanged(n -> firstShade(n).remove("slotOrderBasis")),
        "shades[0].slotOrderBasis",
        Code.REQUIRED);
    ReadResult colorless =
        CollectedProductReader.read(
            patch(
                sample("romand_single_unverified.json"),
                n -> firstOf(n, 1).remove("slotOrderBasis")));
    assertThat(colorless.issues()).isEmpty();
  }

  // --- 색 칸 ---

  @Test
  void slotNameAndNameSourceMustAgree() throws Exception {
    assertSingleIssue(
        readChanged(n -> firstColor(n).put("name", "Sand")),
        "shades[0].colors[0].nameSource",
        Code.INCONSISTENT);
    assertSingleIssue(
        readChanged(n -> firstColor(n).put("nameSource", "SITE_TEXT")),
        "shades[0].colors[0].nameSource",
        Code.INCONSISTENT);
    ReadResult named =
        readChanged(
            n -> {
              firstColor(n).put("name", "Sand");
              firstColor(n).put("nameSource", "IMAGE_PRINT");
            });
    assertThat(named.issues()).isEmpty();
    assertThat(named.product().shades().get(0).colors().get(0).name()).isEqualTo("Sand");
  }

  @Test
  void modelCountedSequenceNumbersAreNotAcceptedAsNameSource() throws Exception {
    assertSingleIssue(
        readChanged(
            n -> {
              firstColor(n).put("name", "1");
              firstColor(n).put("nameSource", "MODEL_INDEX");
            }),
        "shades[0].colors[0].nameSource",
        Code.INVALID_VALUE);
  }

  @Test
  void hexMustBeUppercaseRrggbbOrNull() throws Exception {
    for (String bad : List.of("#1e1b1c", "1E1B1C", "#1E1B1", "#GGGGGG", "#1E1B1CFF")) {
      ReadResult result = readChanged(n -> firstColor(n).put("hex", bad));

      assertThat(paths(result)).as(bad).contains("shades[0].colors[0].hex");
      assertThat(result.product()).isNull();
    }
  }

  @Test
  void slotWithoutColorKeepsEverythingElseNull() throws Exception {
    ReadResult nullHex =
        readChanged(
            n -> {
              firstShade(n).put("colorStatus", "FAILED");
              ObjectNode color = firstColor(n);
              color.putNull("hex");
              color.putNull("colorSource");
              color.putNull("colorQuality");
              color.put("shadeLink", "UNVERIFIED");
            });
    assertThat(nullHex.issues()).isEmpty();
    assertThat(nullHex.product().shades().get(0).colors().get(0).hasColor()).isFalse();

    // 색이 없는데 출처나 품질이 있는 칸은 DB 의 all-or-none 규칙과 맞지 않는다
    ReadResult withSource =
        readChanged(
            n -> {
              firstShade(n).put("colorStatus", "FAILED");
              firstColor(n).putNull("hex");
            });
    assertThat(paths(withSource))
        .contains("shades[0].colors[0].colorSource", "shades[0].colors[0].colorQuality");
  }

  @Test
  void colorSourceAndShadeLinkAreRequiredWithAColorAndMustBeKnown() throws Exception {
    assertSingleIssue(
        readChanged(n -> firstColor(n).remove("colorSource")),
        "shades[0].colors[0].colorSource",
        Code.REQUIRED);
    assertSingleIssue(
        readChanged(n -> firstColor(n).remove("shadeLink")),
        "shades[0].colors[0].shadeLink",
        Code.REQUIRED);
    assertSingleIssue(
        readChanged(n -> firstColor(n).put("colorSource", "OFFICIAL")),
        "shades[0].colors[0].colorSource",
        Code.INVALID_VALUE);
    // SAMPLE 은 개발용 시드에만 있고 수집기는 보내지 않는다
    assertSingleIssue(
        readChanged(n -> firstColor(n).put("colorSource", "SAMPLE")),
        "shades[0].colors[0].colorSource",
        Code.INVALID_VALUE);
  }

  @Test
  void colorQualityRuleDependsOnTheColorSource() throws Exception {
    // 사진에서 얻은 색은 0~1 점수가 필수
    assertSingleIssue(
        readChanged(n -> firstColor(n).remove("colorQuality")),
        "shades[0].colors[0].colorQuality",
        Code.REQUIRED);
    assertSingleIssue(
        readChanged(n -> firstColor(n).put("colorQuality", 1.2)),
        "shades[0].colors[0].colorQuality",
        Code.INVALID_VALUE);
    assertSingleIssue(
        readChanged(n -> firstColor(n).put("colorQuality", "high")),
        "shades[0].colors[0].colorQuality",
        Code.WRONG_TYPE);
    // 사이트 색값과 모델 추정은 점수가 없어야 한다
    for (String source : List.of("SOURCE_VALUE", "LLM_ESTIMATE")) {
      assertSingleIssue(
          readChanged(n -> firstColor(n).put("colorSource", source)),
          "shades[0].colors[0].colorQuality",
          Code.INCONSISTENT);
      ReadResult valid =
          readChanged(
              n -> {
                firstColor(n).put("colorSource", source);
                firstColor(n).putNull("colorQuality");
              });
      assertThat(valid.issues()).as(source).isEmpty();
    }
  }

  @Test
  void evidenceKeyMustBeBuiltFromProductOptionAndSlotOrder() throws Exception {
    assertSingleIssue(
        readChanged(n -> firstColor(n).put("evidenceKey", "other/01-black/1")),
        "shades[0].colors[0].evidenceKey",
        Code.INCONSISTENT);
    assertSingleIssue(
        readChanged(n -> firstColor(n).remove("evidenceKey")),
        "shades[0].colors[0].evidenceKey",
        Code.REQUIRED);
  }

  @Test
  void slotOrderStartsAtOneAndIsUniqueInAShade() throws Exception {
    assertSingleIssue(
        readChanged(
            n -> {
              firstColor(n).put("sortOrder", 0);
              firstColor(n).put("evidenceKey", "example-curl-fix-mascara/01-black/0");
            }),
        "shades[0].colors[0].sortOrder",
        Code.INVALID_VALUE);

    ReadResult duplicate =
        CollectedProductReader.read(
            patch(
                sample("romand_duo_shade.json"),
                n -> {
                  ObjectNode second = (ObjectNode) firstShade(n).path("colors").get(1);
                  second.put("sortOrder", 1);
                  second.put("evidenceKey", "9002/01 예시 듀오 브라운/1");
                }));
    assertSingleIssue(duplicate, "shades[0].colors[1].sortOrder", Code.DUPLICATE);
  }

  @Test
  void everyProblemOfOneItemIsReportedTogether() throws Exception {
    ReadResult result =
        readChanged(
            n -> {
              n.remove("brand");
              n.put("sourceUrl", "nope");
              firstColor(n).put("hex", "red");
            });

    assertThat(paths(result))
        .containsExactlyInAnyOrder("brand", "sourceUrl", "shades[0].colors[0].hex");
  }

  // --- 도우미 ---

  private static ObjectNode patch(ObjectNode node, Consumer<ObjectNode> change) {
    change.accept(node);
    return node;
  }

  private static ObjectNode firstOf(ObjectNode product, int shadeIndex) {
    JsonNode shade = product.path("shades").get(shadeIndex);
    return (ObjectNode) shade;
  }
}
