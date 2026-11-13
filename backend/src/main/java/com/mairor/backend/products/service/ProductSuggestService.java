package com.mairor.backend.products.service;

import com.mairor.backend.products.dto.request.ProductSuggestQuery;
import com.mairor.backend.products.dto.response.ProductSuggestionResponse;
import com.mairor.backend.products.entity.Product;
import com.mairor.backend.products.repository.ProductRepository;
import com.mairor.backend.products.support.CatalogTextNormalizer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 내 화장품 등록의 제품명 자동 완성(S15P31A306-530). 입력한 말이 브랜드+제품명(공백 제거)에 부분 일치하는 카탈로그 제품을 후보로 준다.
 *
 * <p>공백으로 나눈 단어(앞에서 {@value #MAX_WORDS}개까지)가 **모두** 들어 있어야 하고, 이 조건과 정렬을 DB 가 처리한다(제품명이 입력으로 시작 →
 * 짧은 제품명 → 제품명 순). 그래서 후보가 많아도 상위 {@value #POOL_SIZE}건에 앞쪽 후보가 남는다. 회원이 쓴 이름의 별칭은 별칭 한 건이 모든 단어를
 * 만족할 때만 본다. 호수·색이 없는 제품도 후보다. 후보를 고르면 화면이 제품 상세로 호수를 받는다. 쿼리는 제품·별칭 각 1번이다.
 */
@Service
@Transactional(readOnly = true)
public class ProductSuggestService {

  static final int MIN_COMPACT_LENGTH = 2;
  static final int MAX_WORDS = 6;
  private static final int POOL_SIZE = 100;
  private static final char ESCAPE = '!';
  private static final String ANY = "%";

  private final ProductRepository productRepository;

  public ProductSuggestService(ProductRepository productRepository) {
    this.productRepository = productRepository;
  }

  /**
   * @return 이름이 입력과 가까운 순서(입력으로 시작 → 짧은 이름 → 이름 순)의 후보. 입력이 2자 미만이면 빈 목록
   */
  public List<ProductSuggestionResponse> suggest(ProductSuggestQuery query) {
    List<String> words = words(query.q());
    String whole = String.join("", words);
    if (whole.length() < MIN_COMPACT_LENGTH) {
      return List.of();
    }
    List<String> w = patterns(words);
    String prefix = escape(whole) + "%";
    String category = blankToNull(query.category());
    String type = blankToNull(query.type());
    PageRequest pool = PageRequest.of(0, POOL_SIZE);

    Map<UUID, Product> found = new LinkedHashMap<>();
    for (Product p :
        productRepository.findSuggestions(
            w.get(0), w.get(1), w.get(2), w.get(3), w.get(4), w.get(5), prefix, category, type,
            pool)) {
      found.putIfAbsent(p.getId(), p);
    }
    for (Product p :
        productRepository.findSuggestionsByAlias(
            w.get(0), w.get(1), w.get(2), w.get(3), w.get(4), w.get(5), prefix, category, type,
            pool)) {
      found.putIfAbsent(p.getId(), p);
    }
    return found.values().stream()
        .sorted(
            Comparator.comparing((Product p) -> !nameStartsWith(p, whole))
                .thenComparingInt(p -> nameCompact(p).length())
                .thenComparing(ProductSuggestService::nameCompact))
        .limit(query.limitOrDefault())
        .map(ProductSuggestionResponse::of)
        .toList();
  }

  private static List<String> words(String q) {
    String trimmed = CatalogTextNormalizer.trimmed(q);
    if (trimmed.isEmpty()) {
      return List.of();
    }
    return Arrays.stream(CatalogTextNormalizer.normalize(trimmed).split(" "))
        .filter(w -> !w.isEmpty())
        .toList();
  }

  /** 단어마다 LIKE 패턴을 만들고, 모자란 칸은 모두 맞는 {@code %}로 채운다. 6개를 넘는 단어는 보지 않는다. */
  private static List<String> patterns(List<String> words) {
    List<String> patterns = new ArrayList<>();
    for (String word : words.subList(0, Math.min(words.size(), MAX_WORDS))) {
      patterns.add("%" + escape(word) + "%");
    }
    while (patterns.size() < MAX_WORDS) {
      patterns.add(ANY);
    }
    return patterns;
  }

  private static String nameCompact(Product p) {
    return CatalogTextNormalizer.compact(p.getName());
  }

  private static boolean nameStartsWith(Product p, String whole) {
    return nameCompact(p).startsWith(whole);
  }

  private static String escape(String word) {
    StringBuilder out = new StringBuilder();
    for (char c : word.toCharArray()) {
      if (c == '%' || c == '_' || c == ESCAPE) {
        out.append(ESCAPE);
      }
      out.append(c);
    }
    return out.toString();
  }

  private static String blankToNull(String value) {
    return value == null || value.isBlank() ? null : value.trim();
  }
}
