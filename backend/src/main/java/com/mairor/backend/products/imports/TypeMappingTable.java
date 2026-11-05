package com.mairor.backend.products.imports;

import com.mairor.backend.products.support.CatalogTextNormalizer;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import tools.jackson.databind.JsonNode;

/**
 * {@code (출처, 몰 카테고리 경로) → 종류} 매핑표. 파일({@code catalog/type-mapping.json})은 확인된 항목만 담는다.
 *
 * <pre>
 * {"entries": [{"source": "OFFICIAL:romand.co.kr", "categoryPath": ["립"], "type": "LIP_TINT"}]}
 * </pre>
 *
 * 카테고리는 적지 않는다. 종류가 속한 카테고리를 쓰므로 둘이 어긋날 수 없다. 출처와 경로는 정규화해서 비교하고, 경로는 전체가 일치해야 한다. 같은 키가 두 번 있으면 어느
 * 것을 쓸지 알 수 없으므로 읽을 때 거절한다.
 */
public final class TypeMappingTable {

  private final Map<String, String> typeByKey;

  private TypeMappingTable(Map<String, String> typeByKey) {
    this.typeByKey = typeByKey;
  }

  public static TypeMappingTable empty() {
    return new TypeMappingTable(Map.of());
  }

  /**
   * @throws IllegalArgumentException 형식이 틀리거나 같은 키가 두 번 있으면
   */
  public static TypeMappingTable fromJson(JsonNode root) {
    JsonNode entries = root.path("entries");
    if (!entries.isArray()) {
      throw new IllegalArgumentException("entries 배열이 없다");
    }
    Map<String, String> map = new HashMap<>();
    for (int i = 0; i < entries.size(); i++) {
      JsonNode entry = entries.get(i);
      String source = text(entry.path("source"), "entries[" + i + "].source");
      String type = text(entry.path("type"), "entries[" + i + "].type");
      JsonNode path = entry.path("categoryPath");
      if (!path.isArray() || path.isEmpty()) {
        throw new IllegalArgumentException("entries[" + i + "].categoryPath 는 비어 있지 않은 배열이어야 한다");
      }
      List<String> elements = new java.util.ArrayList<>();
      for (JsonNode element : path) {
        elements.add(text(element, "entries[" + i + "].categoryPath"));
      }
      String key = key(source, elements);
      if (map.put(key, type) != null) {
        throw new IllegalArgumentException("같은 키가 두 번 있다: entries[" + i + "]");
      }
    }
    return new TypeMappingTable(Map.copyOf(map));
  }

  /** 종류 코드. 매핑이 없으면 비어 있다. 경로가 비어 있으면 찾지 않는다. */
  public Optional<String> find(String source, List<String> categoryPath) {
    if (source == null || categoryPath == null || categoryPath.isEmpty()) {
      return Optional.empty();
    }
    try {
      return Optional.ofNullable(typeByKey.get(key(source, categoryPath)));
    } catch (IllegalArgumentException e) {
      return Optional.empty();
    }
  }

  public int size() {
    return typeByKey.size();
  }

  private static String key(String source, List<String> path) {
    StringBuilder key = new StringBuilder(CatalogTextNormalizer.normalize(source));
    for (String element : path) {
      key.append('\u0001').append(CatalogTextNormalizer.normalize(element));
    }
    return key.toString();
  }

  private static String text(JsonNode node, String where) {
    if (!node.isString() || CatalogTextNormalizer.trimmed(node.asString("")).isEmpty()) {
      throw new IllegalArgumentException(where + " 는 비어 있지 않은 문자열이어야 한다");
    }
    return node.asString("");
  }
}
