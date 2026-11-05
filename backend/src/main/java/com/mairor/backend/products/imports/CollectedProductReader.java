package com.mairor.backend.products.imports;

import com.mairor.backend.products.entity.ColorSource;
import com.mairor.backend.products.entity.NameSource;
import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.entity.ProductShade;
import com.mairor.backend.products.entity.ProductShadeColor;
import com.mairor.backend.products.entity.SaleStatus;
import com.mairor.backend.products.imports.CollectedProduct.CollectedColor;
import com.mairor.backend.products.imports.CollectedProduct.CollectedShade;
import com.mairor.backend.products.imports.CollectedProduct.ColorStatus;
import com.mairor.backend.products.imports.CollectedProduct.ShadeLink;
import com.mairor.backend.products.imports.CollectedProduct.SlotOrderBasis;
import com.mairor.backend.products.imports.CollectedProduct.VariantHints;
import com.mairor.backend.products.imports.ImportIssue.Code;
import com.mairor.backend.products.support.CatalogTextNormalizer;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;
import tools.jackson.databind.JsonNode;

/**
 * 수집기가 보낸 상품 한 건(JSON)을 읽어 {@link CollectedProduct}로 만들고, 계약({@code
 * shared/catalog-import/README.md}) 규칙을 검사한다.
 *
 * <p>요청 전체가 아니라 **건마다** 검사한다. 한 건이 틀려도 나머지 건은 계속 처리하려고, 문제는 예외가 아니라 {@link ImportIssue} 목록으로 돌려준다.
 * 문제가 하나라도 있으면 {@link ReadResult#product}는 {@code null}이다. 모르는 필드는 무시한다(계약은 {@code
 * contractVersion}으로 올린다).
 *
 * <p>검사하는 것은 형식과 건 안의 일관성뿐이다. 이미 있는 제품인지, 색을 써도 되는지는 판정 단계가 한다. 길이 상한을 넘는 값은 자르지 않고 거절한다.
 */
public final class CollectedProductReader {

  /** 이 판만 읽는다. 다른 판은 그 건만 {@code INVALID} 이다. */
  public static final int SUPPORTED_CONTRACT_VERSION = 1;

  static final int ITEM_KEY_MAX = 100;
  static final int LANGUAGE_MAX = 10;
  static final int CATEGORY_PATH_MAX_ITEMS = 10;
  static final int CATEGORY_PATH_ELEMENT_MAX = 100;
  static final int HINT_MAX = 40;
  static final int SHADES_MAX = 200;
  static final int COLORS_MAX = 30;
  static final int WARNINGS_MAX = 50;
  static final int WARNING_MAX = 100;
  static final int HINT_TEXT_MAX = 200;
  static final int OPTION_ATTRIBUTES_MAX = 20;

  /** {@code OFFICIAL:<도메인>} 또는 {@code WEB:<도메인>}. */
  private static final Pattern SOURCE = Pattern.compile("^(OFFICIAL|WEB):[A-Za-z0-9.-]+$");

  private static final Pattern LANGUAGE = Pattern.compile("^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$");
  private static final Pattern HEX = Pattern.compile("^#[0-9A-F]{6}$");
  private static final Pattern HTTP_URL =
      Pattern.compile("^https?://\\S+$", Pattern.CASE_INSENSITIVE);

  /** 수집기가 값을 보내서는 안 되는 출처. {@code SAMPLE}은 개발용 시드에만 쓴다. */
  private static final Set<ColorSource> NOT_COLLECTABLE = Set.of(ColorSource.SAMPLE);

  private CollectedProductReader() {}

  /**
   * @param itemKey 건의 위치. 읽지 못했으면 {@code null}
   * @param product 검사를 통과한 값. 문제가 있으면 {@code null}
   * @param issues 찾은 문제. 비어 있으면 통과
   */
  public record ReadResult(String itemKey, CollectedProduct product, List<ImportIssue> issues) {

    public boolean isValid() {
      return issues.isEmpty();
    }
  }

  public static ReadResult read(JsonNode root) {
    return new Reader().run(root);
  }

  private static final class Reader {

    private final List<ImportIssue> issues = new ArrayList<>();

    ReadResult run(JsonNode root) {
      if (root == null || !root.isObject()) {
        issue("$", Code.WRONG_TYPE, "상품은 JSON 객체여야 한다");
        return result(null, null);
      }
      String itemKey = tryItemKey(root);
      int version = contractVersion(root);
      if (version != SUPPORTED_CONTRACT_VERSION) {
        return result(itemKey, null);
      }

      String key = reqString(root, "itemKey", "itemKey", ITEM_KEY_MAX);
      String source = reqString(root, "source", "source", Product.SOURCE_MAX_LENGTH);
      if (source != null && !SOURCE.matcher(source).matches()) {
        issue("source", Code.INVALID_FORMAT, "OFFICIAL:<도메인> 또는 WEB:<도메인> 이어야 한다");
      }
      String sourceProductId =
          reqRawString(
              root, "sourceProductId", "sourceProductId", Product.SOURCE_PRODUCT_ID_MAX_LENGTH);
      String sourceUrl = reqString(root, "sourceUrl", "sourceUrl", Product.SOURCE_URL_MAX_LENGTH);
      if (sourceUrl != null && !HTTP_URL.matcher(sourceUrl).matches()) {
        issue("sourceUrl", Code.INVALID_FORMAT, "http(s) 주소여야 한다");
      }
      String language = reqString(root, "sourceLanguage", "sourceLanguage", LANGUAGE_MAX);
      if (language != null && !LANGUAGE.matcher(language).matches()) {
        issue("sourceLanguage", Code.INVALID_FORMAT, "언어 코드여야 한다 (예: ko, en, ja)");
      }
      OffsetDateTime collectedAt = collectedAt(root);
      String brand = reqString(root, "brand", "brand", Product.BRAND_MAX_LENGTH);
      String name = reqString(root, "name", "name", Product.NAME_MAX_LENGTH);
      List<String> categoryPath = categoryPath(root);
      String categoryHint = optString(root, "categoryHint", "categoryHint", HINT_MAX);
      String typeHint = optString(root, "typeHint", "typeHint", HINT_MAX);
      String imageUrl = optString(root, "imageUrl", "imageUrl", Product.IMAGE_URL_MAX_LENGTH);
      SaleStatus saleStatus =
          enumValue(root, "saleStatus", "saleStatus", SaleStatus.class, false, Set.of());
      List<CollectedShade> shades = shades(root, sourceProductId);
      List<String> warnings = warnings(root);

      if (!issues.isEmpty()) {
        return result(itemKey, null);
      }
      return result(
          itemKey,
          new CollectedProduct(
              version,
              key,
              source,
              sourceProductId,
              sourceUrl,
              language,
              collectedAt,
              brand,
              name,
              categoryPath,
              categoryHint,
              typeHint,
              imageUrl,
              saleStatus,
              shades,
              warnings));
    }

    private ReadResult result(String itemKey, CollectedProduct product) {
      return new ReadResult(itemKey, issues.isEmpty() ? product : null, List.copyOf(issues));
    }

    /** 다른 필드가 틀려도 결과 보고에 건의 위치를 쓸 수 있게 따로 읽는다. 문제는 여기서 보고하지 않는다. */
    private static String tryItemKey(JsonNode root) {
      JsonNode node = root.path("itemKey");
      if (!node.isString()) {
        return null;
      }
      String key = CatalogTextNormalizer.trimmed(node.asString(""));
      return key.isEmpty() || key.length() > ITEM_KEY_MAX ? null : key;
    }

    private int contractVersion(JsonNode root) {
      JsonNode node = root.path("contractVersion");
      if (node.isMissingNode() || node.isNull()) {
        issue("contractVersion", Code.REQUIRED, "계약 판이 없다");
        return -1;
      }
      if (!node.isIntegralNumber() || !node.canConvertToInt()) {
        issue("contractVersion", Code.WRONG_TYPE, "정수여야 한다");
        return -1;
      }
      int version = node.intValue();
      if (version != SUPPORTED_CONTRACT_VERSION) {
        issue(
            "contractVersion",
            Code.UNSUPPORTED_CONTRACT_VERSION,
            "지원하는 판은 " + SUPPORTED_CONTRACT_VERSION + " 뿐이다");
      }
      return version;
    }

    private OffsetDateTime collectedAt(JsonNode root) {
      String text = reqString(root, "collectedAt", "collectedAt", 40);
      if (text == null) {
        return null;
      }
      try {
        return OffsetDateTime.parse(text);
      } catch (DateTimeParseException e) {
        issue("collectedAt", Code.INVALID_FORMAT, "시간대가 있는 ISO-8601 시각이어야 한다");
        return null;
      }
    }

    private List<String> categoryPath(JsonNode root) {
      JsonNode node = root.path("sourceCategoryPath");
      if (node.isMissingNode() || node.isNull()) {
        return List.of();
      }
      if (!node.isArray()) {
        issue("sourceCategoryPath", Code.WRONG_TYPE, "문자열 배열이어야 한다");
        return List.of();
      }
      if (node.size() > CATEGORY_PATH_MAX_ITEMS) {
        issue("sourceCategoryPath", Code.TOO_LONG, "항목은 " + CATEGORY_PATH_MAX_ITEMS + "개까지다");
        return List.of();
      }
      List<String> path = new ArrayList<>();
      for (int i = 0; i < node.size(); i++) {
        String element =
            stringElement(node.get(i), "sourceCategoryPath[" + i + "]", CATEGORY_PATH_ELEMENT_MAX);
        if (element != null) {
          path.add(element);
        }
      }
      return List.copyOf(path);
    }

    private List<String> warnings(JsonNode root) {
      JsonNode node = root.path("warnings");
      if (node.isMissingNode() || node.isNull()) {
        return List.of();
      }
      if (!node.isArray()) {
        issue("warnings", Code.WRONG_TYPE, "문자열 배열이어야 한다");
        return List.of();
      }
      if (node.size() > WARNINGS_MAX) {
        issue("warnings", Code.TOO_LONG, "항목은 " + WARNINGS_MAX + "개까지다");
        return List.of();
      }
      List<String> warnings = new ArrayList<>();
      for (int i = 0; i < node.size(); i++) {
        String warning = stringElement(node.get(i), "warnings[" + i + "]", WARNING_MAX);
        if (warning != null) {
          warnings.add(warning);
        }
      }
      return List.copyOf(warnings);
    }

    private List<CollectedShade> shades(JsonNode root, String sourceProductId) {
      JsonNode node = root.path("shades");
      if (node.isMissingNode() || node.isNull()) {
        return List.of();
      }
      if (!node.isArray()) {
        issue("shades", Code.WRONG_TYPE, "배열이어야 한다");
        return List.of();
      }
      if (node.size() > SHADES_MAX) {
        issue("shades", Code.TOO_LONG, "호수는 " + SHADES_MAX + "개까지다");
        return List.of();
      }
      List<CollectedShade> shades = new ArrayList<>();
      Set<String> optionIds = new HashSet<>();
      for (int i = 0; i < node.size(); i++) {
        CollectedShade shade = shade(node.get(i), "shades[" + i + "]", sourceProductId);
        if (shade == null) {
          continue;
        }
        if (!optionIds.add(shade.sourceOptionId())) {
          issue("shades[" + i + "].sourceOptionId", Code.DUPLICATE, "같은 옵션 값이 한 건에 두 번 있다");
        }
        shades.add(shade);
      }
      return List.copyOf(shades);
    }

    private CollectedShade shade(JsonNode node, String path, String sourceProductId) {
      if (!node.isObject()) {
        issue(path, Code.WRONG_TYPE, "객체여야 한다");
        return null;
      }
      String optionId =
          reqRawString(
              node,
              "sourceOptionId",
              path + ".sourceOptionId",
              ProductShade.SOURCE_OPTION_MAX_LENGTH);
      String name = reqString(node, "name", path + ".name", ProductShade.NAME_MAX_LENGTH);
      Integer sortOrder = reqInt(node, "sortOrder", path + ".sortOrder", 0);
      ColorStatus status =
          enumValue(node, "colorStatus", path + ".colorStatus", ColorStatus.class, true, Set.of());
      VariantHints hints = variantHints(node.path("variantHints"), path + ".variantHints");
      int issuesBeforeColors = issues.size();
      List<CollectedColor> colors = colors(node, path, sourceProductId, optionId);
      // 칸 하나가 거절되면 목록에서 빠져 상태와 어긋나 보인다. 그 어긋남은 원인이 아니라 결과라서 따로 보고하지 않는다
      boolean colorsAreClean = issues.size() == issuesBeforeColors;
      SlotOrderBasis basis =
          enumValue(
              node,
              "slotOrderBasis",
              path + ".slotOrderBasis",
              SlotOrderBasis.class,
              !colors.isEmpty(),
              Set.of());

      if (status != null && colorsAreClean) {
        boolean anyColor = colors.stream().anyMatch(CollectedColor::hasColor);
        if (status == ColorStatus.EXTRACTED && !anyColor) {
          issue(path + ".colorStatus", Code.INCONSISTENT, "EXTRACTED 인데 색이 있는 칸이 없다");
        } else if (status != ColorStatus.EXTRACTED && anyColor) {
          issue(path + ".colorStatus", Code.INCONSISTENT, status + " 인데 색이 있는 칸이 있다");
        }
      }
      if (optionId == null || name == null || sortOrder == null || status == null) {
        return null;
      }
      return new CollectedShade(optionId, name, sortOrder, basis, status, hints, colors);
    }

    private VariantHints variantHints(JsonNode node, String path) {
      if (node.isMissingNode() || node.isNull()) {
        return null;
      }
      if (!node.isObject()) {
        issue(path, Code.WRONG_TYPE, "객체여야 한다");
        return null;
      }
      Map<String, String> attributes = null;
      JsonNode raw = node.path("optionAttributes");
      if (raw.isObject()) {
        if (raw.size() > OPTION_ATTRIBUTES_MAX) {
          issue(path + ".optionAttributes", Code.TOO_LONG, "항목은 " + OPTION_ATTRIBUTES_MAX + "개까지다");
        } else {
          attributes = new LinkedHashMap<>();
          for (Map.Entry<String, JsonNode> entry : raw.properties()) {
            String value =
                scalarText(
                    entry.getValue(), path + ".optionAttributes." + entry.getKey(), HINT_TEXT_MAX);
            if (value != null) {
              attributes.put(entry.getKey(), value);
            }
          }
        }
      } else if (!raw.isMissingNode() && !raw.isNull()) {
        issue(path + ".optionAttributes", Code.WRONG_TYPE, "객체이거나 null 이어야 한다");
      }
      return new VariantHints(
          scalarText(node.path("volume"), path + ".volume", HINT_TEXT_MAX),
          scalarText(node.path("composition"), path + ".composition", HINT_TEXT_MAX),
          scalarText(node.path("formulation"), path + ".formulation", HINT_TEXT_MAX),
          attributes == null ? null : Map.copyOf(attributes),
          scalarText(node.path("listPrice"), path + ".listPrice", HINT_TEXT_MAX));
    }

    private List<CollectedColor> colors(
        JsonNode shade, String shadePath, String sourceProductId, String sourceOptionId) {
      JsonNode node = shade.path("colors");
      if (node.isMissingNode() || node.isNull()) {
        return List.of();
      }
      if (!node.isArray()) {
        issue(shadePath + ".colors", Code.WRONG_TYPE, "배열이어야 한다");
        return List.of();
      }
      if (node.size() > COLORS_MAX) {
        issue(shadePath + ".colors", Code.TOO_LONG, "칸은 " + COLORS_MAX + "개까지다");
        return List.of();
      }
      List<CollectedColor> colors = new ArrayList<>();
      Set<Integer> orders = new HashSet<>();
      for (int i = 0; i < node.size(); i++) {
        String path = shadePath + ".colors[" + i + "]";
        CollectedColor color = color(node.get(i), path, sourceProductId, sourceOptionId);
        if (color == null) {
          continue;
        }
        if (!orders.add(color.sortOrder())) {
          issue(path + ".sortOrder", Code.DUPLICATE, "한 호수 안에서 칸 순서가 겹친다");
        }
        colors.add(color);
      }
      return List.copyOf(colors);
    }

    private CollectedColor color(
        JsonNode node, String path, String sourceProductId, String sourceOptionId) {
      if (!node.isObject()) {
        issue(path, Code.WRONG_TYPE, "객체여야 한다");
        return null;
      }
      Integer sortOrder = reqInt(node, "sortOrder", path + ".sortOrder", 1);
      String name = optString(node, "name", path + ".name", ProductShadeColor.NAME_MAX_LENGTH);
      NameSource nameSource =
          enumValue(node, "nameSource", path + ".nameSource", NameSource.class, true, Set.of());
      if (nameSource != null) {
        if (name != null && nameSource == NameSource.NONE) {
          issue(path + ".nameSource", Code.INCONSISTENT, "이름이 있으면 근거는 NONE 일 수 없다");
        } else if (name == null && nameSource != NameSource.NONE) {
          issue(path + ".nameSource", Code.INCONSISTENT, "이름이 없으면 근거는 NONE 이어야 한다");
        }
      }

      String hex = optString(node, "hex", path + ".hex", 7);
      if (hex != null && !HEX.matcher(hex).matches()) {
        issue(path + ".hex", Code.INVALID_FORMAT, "#RRGGBB 대문자여야 한다");
      }
      boolean hasColor = hex != null;
      ColorSource colorSource =
          enumValue(
              node,
              "colorSource",
              path + ".colorSource",
              ColorSource.class,
              hasColor,
              NOT_COLLECTABLE);
      if (!hasColor && colorSource != null) {
        issue(path + ".colorSource", Code.INCONSISTENT, "색이 없는 칸에는 출처를 쓰지 않는다");
      }
      ShadeLink shadeLink =
          enumValue(node, "shadeLink", path + ".shadeLink", ShadeLink.class, hasColor, Set.of());
      Double quality = colorQuality(node, path, hasColor, colorSource);

      String evidenceKey = reqRawString(node, "evidenceKey", path + ".evidenceKey", 400);
      if (evidenceKey != null
          && sortOrder != null
          && sourceProductId != null
          && sourceOptionId != null) {
        String expected = sourceProductId + "/" + sourceOptionId + "/" + sortOrder;
        if (!evidenceKey.equals(expected)) {
          issue(
              path + ".evidenceKey",
              Code.INCONSISTENT,
              "<sourceProductId>/<sourceOptionId>/<칸 sortOrder> 꼴이어야 한다");
        }
      }
      if (sortOrder == null || nameSource == null) {
        return null;
      }
      return new CollectedColor(
          sortOrder, name, nameSource, hex, colorSource, shadeLink, quality, evidenceKey);
    }

    /** 사진에서 얻은 색만 0~1 품질을 가진다. 사이트 색값·모델 추정·색 없음은 {@code null} 이다. */
    private Double colorQuality(JsonNode node, String path, boolean hasColor, ColorSource source) {
      String p = path + ".colorQuality";
      JsonNode raw = node.path("colorQuality");
      boolean present = !raw.isMissingNode() && !raw.isNull();
      boolean photo =
          hasColor
              && source != null
              && source != ColorSource.SOURCE_VALUE
              && source != ColorSource.LLM_ESTIMATE;
      if (!present) {
        if (photo) {
          issue(p, Code.REQUIRED, "사진에서 얻은 색은 품질 점수가 있어야 한다");
        }
        return null;
      }
      if (!raw.isNumber()) {
        issue(p, Code.WRONG_TYPE, "숫자여야 한다");
        return null;
      }
      double value = raw.doubleValue();
      if (!hasColor || (source != null && !photo)) {
        issue(p, Code.INCONSISTENT, "사진에서 얻은 색에만 품질 점수를 쓴다");
        return null;
      }
      if (Double.isNaN(value) || value < 0.0 || value > 1.0) {
        issue(p, Code.INVALID_VALUE, "0~1 사이여야 한다");
        return null;
      }
      return value;
    }

    // --- 필드 읽기 ---

    /** 앞뒤 공백을 지운 필수 문자열. 비었거나 길면 문제로 기록하고 {@code null}. */
    private String reqString(JsonNode parent, String field, String path, int max) {
      return string(parent.path(field), path, max, true, true);
    }

    /** 가공하지 않는 필수 문자열(키로 쓰는 값). 공백만 있으면 비었다고 본다. */
    private String reqRawString(JsonNode parent, String field, String path, int max) {
      return string(parent.path(field), path, max, true, false);
    }

    private String optString(JsonNode parent, String field, String path, int max) {
      return string(parent.path(field), path, max, false, true);
    }

    private String string(JsonNode node, String path, int max, boolean required, boolean trim) {
      if (node.isMissingNode() || node.isNull()) {
        if (required) {
          issue(path, Code.REQUIRED, "값이 없다");
        }
        return null;
      }
      if (!node.isString()) {
        issue(path, Code.WRONG_TYPE, "문자열이어야 한다");
        return null;
      }
      String text = node.asString("");
      String trimmed = CatalogTextNormalizer.trimmed(text);
      if (trimmed.isEmpty()) {
        if (required) {
          issue(path, Code.REQUIRED, "비어 있다");
        }
        return null;
      }
      String value = trim ? trimmed : text;
      if (value.length() > max) {
        issue(path, Code.TOO_LONG, max + "자를 넘는다");
        return null;
      }
      return value;
    }

    private String stringElement(JsonNode node, String path, int max) {
      if (!node.isString()) {
        issue(path, Code.WRONG_TYPE, "문자열이어야 한다");
        return null;
      }
      String trimmed = CatalogTextNormalizer.trimmed(node.asString(""));
      if (trimmed.isEmpty()) {
        return null;
      }
      if (trimmed.length() > max) {
        issue(path, Code.TOO_LONG, max + "자를 넘는다");
        return null;
      }
      return trimmed;
    }

    /** 사이트 원문이라 문자열이나 숫자를 모두 받아 문자열로 둔다. {@code null}·없음은 {@code null}. */
    private String scalarText(JsonNode node, String path, int max) {
      if (node.isMissingNode() || node.isNull()) {
        return null;
      }
      if (!node.isString() && !node.isNumber()) {
        issue(path, Code.WRONG_TYPE, "문자열이거나 숫자여야 한다");
        return null;
      }
      String text = CatalogTextNormalizer.trimmed(node.asString(""));
      if (text.isEmpty()) {
        return null;
      }
      if (text.length() > max) {
        issue(path, Code.TOO_LONG, max + "자를 넘는다");
        return null;
      }
      return text;
    }

    private Integer reqInt(JsonNode parent, String field, String path, int min) {
      JsonNode node = parent.path(field);
      if (node.isMissingNode() || node.isNull()) {
        issue(path, Code.REQUIRED, "값이 없다");
        return null;
      }
      if (!node.isIntegralNumber() || !node.canConvertToInt()) {
        issue(path, Code.WRONG_TYPE, "정수여야 한다");
        return null;
      }
      int value = node.intValue();
      if (value < min) {
        issue(path, Code.INVALID_VALUE, min + " 이상이어야 한다");
        return null;
      }
      return value;
    }

    private <E extends Enum<E>> E enumValue(
        JsonNode parent,
        String field,
        String path,
        Class<E> type,
        boolean required,
        Set<E> forbidden) {
      JsonNode node = parent.path(field);
      if (node.isMissingNode() || node.isNull()) {
        if (required) {
          issue(path, Code.REQUIRED, "값이 없다");
        }
        return null;
      }
      if (!node.isString()) {
        issue(path, Code.WRONG_TYPE, "문자열이어야 한다");
        return null;
      }
      try {
        E value = Enum.valueOf(type, node.asString(""));
        if (forbidden.contains(value)) {
          issue(path, Code.INVALID_VALUE, "쓸 수 없는 값이다");
          return null;
        }
        return value;
      } catch (IllegalArgumentException e) {
        issue(path, Code.INVALID_VALUE, "허용 목록에 없는 값이다");
        return null;
      }
    }

    private void issue(String path, Code code, String message) {
      issues.add(new ImportIssue(path, code, message));
    }
  }
}
