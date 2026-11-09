package com.mairor.backend.products.imports;

import com.mairor.backend.products.entity.ImportItemOutcome;
import com.mairor.backend.products.imports.CatalogImportRunService.RunView;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 카탈로그 적재의 통계. 서로 다른 두 가지를 따로 낸다.
 *
 * <ul>
 *   <li><b>실행 통계</b>({@link #runStats}): 그 실행이 어떻게 끝났는가. 건의 처리 결과별 개수, 일부만 반영한 건, 저장하거나 바꾼 색 칸 수,
 *       사유별 개수, 문제가 난 건 몇 개. 실행이 {@code COMPLETED}로 끝났어도 틀린 건·실패한 건은 그대로 드러난다(일부 오류가 전체 성공으로 숨지
 *       않는다).
 *   <li><b>현재 품질 통계</b>({@link #quality}): 지금 카탈로그의 색이 어떤 상태인가. 어느 실행이 만들었는지와 상관없이 호수·색 칸이 사용 가능,
 *       기준 미달, 색 미확보 중 어디에 있는지 센다. 임계값이 바뀌거나 재수집으로 색이 바뀌면 숫자가 달라진다.
 * </ul>
 *
 * 이 값은 조회용이라 아무것도 바꾸지 않는다. 사용 가능은 {@code AUTO_APPROVED}·{@code APPROVED}, 기준 미달은 {@code
 * BELOW_THRESHOLD}·{@code REJECTED}(값은 있지만 서비스에 쓰지 않음), 색 미확보는 HEX 가 없는 칸이다.
 */
@Service
public class CatalogImportStatsService {

  /** 문제가 난 건(틀린 건, 처리 중 오류가 난 건)을 몇 건까지 보여 줄지. 전체 개수는 따로 센다. */
  public static final int MAX_PROBLEMS = 20;

  private static final String USABLE = "c.review_status in ('AUTO_APPROVED', 'APPROVED')";
  private static final String UNUSABLE = "c.review_status in ('BELOW_THRESHOLD', 'REJECTED')";

  private final JdbcTemplate jdbc;
  private final CatalogImportRunService runs;

  public CatalogImportStatsService(JdbcTemplate jdbc, CatalogImportRunService runs) {
    this.jdbc = jdbc;
    this.runs = runs;
  }

  /**
   * 한 실행의 통계.
   *
   * @param byOutcome 처리 결과별 건수. 한 건도 없는 결과도 0으로 포함한다
   * @param created 새 제품으로 반영한 건
   * @param updated 기존 제품을 갱신한 건
   * @param skipped 반영하지 않은 건: 오래된 수집, 다른 출처의 같은 제품, 분류 불가
   * @param failed 틀리거나 처리 중 오류가 난 건
   * @param partial 일부만 반영했거나 기존 값을 지킨 사유가 있는 건
   * @param colorsApplied 저장하거나 바꾼 색 칸 수의 합
   * @param reasons 사유 코드별 건수
   * @param problems 문제가 난 건의 앞부분
   */
  public record RunStats(
      RunView run,
      int total,
      Map<ImportItemOutcome, Integer> byOutcome,
      int created,
      int updated,
      int skipped,
      int failed,
      int partial,
      long colorsApplied,
      Map<String, Integer> reasons,
      List<Problem> problems,
      int problemCount) {}

  /** 문제가 난 건 하나. */
  public record Problem(
      String itemKey, ImportItemOutcome outcome, List<String> reasons, String message) {}

  /**
   * 현재 카탈로그의 색 품질.
   *
   * @param source 센 범위. 모든 출처면 {@code null}
   * @param usableBySource 사용 가능한 색 칸의 색 출처별 개수
   */
  public record Quality(
      String source,
      int products,
      Counts shades,
      Counts slots,
      Map<String, Integer> usableBySource) {}

  /**
   * 개수와 비율.
   *
   * @param total 전체
   * @param usable 사용 가능. 호수는 사용 가능한 칸이 하나라도 있는 호수
   * @param belowThreshold 기준 미달. 호수는 사용 가능한 칸은 없지만 값이 있는 칸이 있는 호수
   * @param withoutColor 색 미확보. 호수는 값이 있는 칸이 하나도 없는 호수(칸이 없는 호수 포함)
   * @param usableRatio {@code usable / total}. 전체가 0이면 {@code null}
   * @param belowThresholdRatio {@code belowThreshold / total}
   * @param withoutColorRatio {@code withoutColor / total}
   */
  public record Counts(
      int total,
      int usable,
      int belowThreshold,
      int withoutColor,
      Double usableRatio,
      Double belowThresholdRatio,
      Double withoutColorRatio) {

    static Counts of(int total, int usable, int belowThreshold, int withoutColor) {
      return new Counts(
          total,
          usable,
          belowThreshold,
          withoutColor,
          ratio(usable, total),
          ratio(belowThreshold, total),
          ratio(withoutColor, total));
    }

    private static Double ratio(int part, int total) {
      return total == 0 ? null : Math.round(part * 10000.0 / total) / 10000.0;
    }
  }

  /**
   * 한 실행의 통계를 읽는다.
   *
   * @throws CatalogImportRunNotFoundException 실행이 없으면
   */
  @Transactional(readOnly = true)
  public RunStats runStats(UUID runId) {
    RunView run = runs.get(runId);
    Map<ImportItemOutcome, Integer> byOutcome = new LinkedHashMap<>();
    for (ImportItemOutcome outcome : ImportItemOutcome.values()) {
      byOutcome.put(outcome, 0);
    }
    int[] partial = {0};
    long[] colors = {0};
    jdbc.query(
        "select outcome, count(*) as n, count(*) filter (where partial) as partial,"
            + " coalesce(sum(colors_applied), 0) as colors"
            + " from catalog_import_items where run_id = ? group by outcome",
        rs -> {
          byOutcome.put(ImportItemOutcome.valueOf(rs.getString("outcome")), rs.getInt("n"));
          partial[0] += rs.getInt("partial");
          colors[0] += rs.getLong("colors");
        },
        runId);

    Map<String, Integer> reasons = new LinkedHashMap<>();
    jdbc.query(
        "select r as reason, count(*) as n from catalog_import_items i,"
            + " unnest(string_to_array(i.reasons, ',')) as r"
            + " where i.run_id = ? and i.reasons <> '' group by r order by n desc, r",
        rs -> {
          reasons.put(rs.getString("reason"), rs.getInt("n"));
        },
        runId);

    List<Problem> problems = new ArrayList<>();
    jdbc.query(
        "select item_key, outcome, reasons, message from catalog_import_items"
            + " where run_id = ? and outcome in ('INVALID', 'FAILED')"
            + " order by item_key limit ?",
        rs -> {
          String joined = rs.getString("reasons");
          problems.add(
              new Problem(
                  rs.getString("item_key"),
                  ImportItemOutcome.valueOf(rs.getString("outcome")),
                  joined.isEmpty() ? List.of() : List.of(joined.split(",")),
                  rs.getString("message")));
        },
        runId,
        MAX_PROBLEMS);

    int total = byOutcome.values().stream().mapToInt(Integer::intValue).sum();
    int failed = byOutcome.get(ImportItemOutcome.INVALID) + byOutcome.get(ImportItemOutcome.FAILED);
    int skipped =
        byOutcome.get(ImportItemOutcome.STALE)
            + byOutcome.get(ImportItemOutcome.AMBIGUOUS)
            + byOutcome.get(ImportItemOutcome.UNCLASSIFIED);
    return new RunStats(
        run,
        total,
        byOutcome,
        byOutcome.get(ImportItemOutcome.NEW),
        byOutcome.get(ImportItemOutcome.UPDATE),
        skipped,
        failed,
        partial[0],
        colors[0],
        reasons,
        List.copyOf(problems),
        failed);
  }

  /**
   * 지금 카탈로그의 색 품질을 센다.
   *
   * @param source 이 출처({@code products.source} 값 그대로)의 제품만 센다. 모든 출처면 {@code null}
   */
  @Transactional(readOnly = true)
  public Quality quality(String source) {
    String where = source == null ? "" : " where p.source = ?";
    Object[] args = source == null ? new Object[0] : new Object[] {source};

    int products =
        jdbc.queryForObject("select count(*) from products p" + where, Integer.class, args);

    int[] slot = new int[4];
    jdbc.query(
        "select count(*) as total,"
            + " count(*) filter (where "
            + USABLE
            + ") as usable,"
            + " count(*) filter (where "
            + UNUSABLE
            + ") as unusable,"
            + " count(*) filter (where c.color_hex is null) as without"
            + " from product_shade_colors c join product_shades s on s.id = c.shade_id"
            + " join products p on p.id = s.product_id"
            + where,
        rs -> {
          slot[0] = rs.getInt("total");
          slot[1] = rs.getInt("usable");
          slot[2] = rs.getInt("unusable");
          slot[3] = rs.getInt("without");
        },
        args);

    int[] shade = new int[4];
    jdbc.query(
        "select count(*) as total,"
            + " count(*) filter (where t.usable > 0) as usable,"
            + " count(*) filter (where t.usable = 0 and t.colored > 0) as unusable,"
            + " count(*) filter (where t.colored = 0) as without"
            + " from (select s.id,"
            + " count(c.id) filter (where "
            + USABLE
            + ") as usable,"
            + " count(c.id) filter (where c.color_hex is not null) as colored"
            + " from product_shades s join products p on p.id = s.product_id"
            + " left join product_shade_colors c on c.shade_id = s.id"
            + where
            + " group by s.id) t",
        rs -> {
          shade[0] = rs.getInt("total");
          shade[1] = rs.getInt("usable");
          shade[2] = rs.getInt("unusable");
          shade[3] = rs.getInt("without");
        },
        args);

    Map<String, Integer> bySource = new LinkedHashMap<>();
    jdbc.query(
        "select c.color_source as color_source, count(*) as n"
            + " from product_shade_colors c join product_shades s on s.id = c.shade_id"
            + " join products p on p.id = s.product_id"
            + " where "
            + USABLE
            + (source == null ? "" : " and p.source = ?")
            + " group by c.color_source order by n desc, c.color_source",
        rs -> {
          bySource.put(rs.getString("color_source"), rs.getInt("n"));
        },
        args);

    return new Quality(
        source,
        products,
        Counts.of(shade[0], shade[1], shade[2], shade[3]),
        Counts.of(slot[0], slot[1], slot[2], slot[3]),
        bySource);
  }
}
