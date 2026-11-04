package com.mairor.backend.analysis.notify;

import java.util.Objects;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * 분석 작업 상태가 바뀌었다고 DB({@code pg_notify})로 알린다(ADR-012 「분석 상태 전달 규칙」). 상태를 바꾸는 프로세스(worker·AI 콜백을 받은
 * api)와 회원이 SSE 로 붙어 있는 api 가 달라도, 모든 api 가 같은 DB 에서 이 알림을 받아 그 작업을 다시 읽어 보낸다.
 *
 * <p>알림에는 작업 ID 만 담는다. 내용은 받은 쪽이 DB 에서 읽는다(DB 가 유일한 원본). 상태를 저장하는 트랜잭션 안에서 부른다. PostgreSQL 은 커밋될 때만
 * 알림을 전달하므로 저장되지 않은 상태가 나가지 않고, 같은 트랜잭션의 같은 알림은 하나로 합친다.
 */
@Component
public class AnalysisJobNotifier {

  /** 알림 채널. 받는 쪽은 {@code LISTEN analysis_job} 한다. */
  public static final String CHANNEL = "analysis_job";

  private final JdbcTemplate jdbc;

  AnalysisJobNotifier(JdbcTemplate jdbc) {
    this.jdbc = jdbc;
  }

  /**
   * @throws org.springframework.transaction.IllegalTransactionStateException 트랜잭션 밖에서 부르면. 커밋과 묶이지
   *     않은 알림은 저장되지 않은 상태를 알릴 수 있다
   */
  @Transactional(propagation = Propagation.MANDATORY)
  public void changed(UUID jobId) {
    Objects.requireNonNull(jobId, "jobId");
    jdbc.query("select pg_notify(?, ?)", rs -> null, CHANNEL, jobId.toString());
  }
}
