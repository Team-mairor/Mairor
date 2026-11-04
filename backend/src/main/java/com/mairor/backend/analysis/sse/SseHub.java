package com.mairor.backend.analysis.sse;

import com.mairor.backend.analysis.dto.response.AnalysisJobStatusResponse;
import com.mairor.backend.analysis.service.AnalysisJobStatusService;
import com.mairor.backend.analysis.service.AnalysisJobStatusView;
import java.io.IOException;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.locks.ReentrantLock;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Profile;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * 분석 상태 SSE 연결을 작업별로 들고 있다가 상태가 바뀌면 보낸다(ADR-012 「분석 상태 전달 규칙」). api 프로세스에서만 뜬다.
 *
 * <p><b>순서</b>: 작업마다 잠금 하나를 두고, 그 작업으로 보내는 일(연결 직후 첫 전송, 변경 알림, LISTEN 재연결 뒤 재전송, 주기 맞추기, ping)은 모두
 * 이 잠금 안에서 한다. 상태는 잠금을 얻은 뒤 DB 에서 새로 읽는다. 미리 읽어 둔 상태를 나중에 보내지 않으므로, 여러 경로가 겹쳐도 과거 상태가 뒤늦게 가지 않는다.
 * 마지막으로 보낸 상태와 같으면 다시 보내지 않는다(연결 직후 첫 전송은 예외).
 *
 * <p>연결을 등록한 뒤 DB 를 읽는다. 이 순서라야 연결 직전에 끝난 작업도 놓치지 않는다. 더 바뀌지 않는 상태(실패·승인·반려)를 보낸 뒤 그 작업의 연결을 모두
 * 닫는다. 검수 대기에서는 열어 두고 FE 가 화면을 떠날 때 닫는다.
 *
 * <p>앱이 내려갈 때는 graceful shutdown 이 요청을 기다리기 전에 연결을 먼저 닫는다({@link #getPhase()}). 닫힌 FE 는 다시 붙어 다른
 * 슬롯으로 간다.
 */
@Component
@Profile("!worker")
public class SseHub implements SmartLifecycle {

  /** SSE 이벤트 이름. FE 는 {@code addEventListener("status", …)}로 받는다. */
  public static final String EVENT = "status";

  private static final Logger log = LoggerFactory.getLogger(SseHub.class);

  private final AnalysisJobStatusService statuses;
  private final NamedParameterJdbcTemplate jdbc;
  private final SseProperties properties;
  private final Map<UUID, Channel> channels = new ConcurrentHashMap<>();
  private volatile boolean running;

  SseHub(
      AnalysisJobStatusService statuses,
      NamedParameterJdbcTemplate jdbc,
      SseProperties properties) {
    this.statuses = statuses;
    this.jdbc = jdbc;
    this.properties = properties;
  }

  /** 작업 하나로 열린 연결들. 보내는 일은 모두 {@link #lock} 안에서 한다. */
  private static final class Channel {
    final ReentrantLock lock = new ReentrantLock();
    final List<SseEmitter> emitters = new CopyOnWriteArrayList<>();
    volatile AnalysisJobStatusView lastSent;
    volatile String fingerprint;
  }

  /**
   * 연결을 등록하고 지금 상태를 먼저 보낸다. 권한은 부르는 쪽이 먼저 확인한다.
   *
   * @return 열린 연결. 이미 끝난 작업이면 상태를 하나 보내고 닫힌다
   */
  public SseEmitter subscribe(UUID jobId) {
    SseEmitter emitter = new SseEmitter(properties.timeout().toMillis());
    if (!running) {
      // 내려가는 중이면 받지 않는다. FE 는 다시 붙어 다른 슬롯으로 간다
      emitter.complete();
      return emitter;
    }
    emitter.onCompletion(() -> remove(jobId, emitter));
    emitter.onTimeout(emitter::complete);
    emitter.onError(error -> remove(jobId, emitter));
    Channel channel =
        channels.compute(
            jobId,
            (id, existing) -> {
              Channel c = existing == null ? new Channel() : existing;
              c.emitters.add(emitter);
              return c;
            });
    channel.lock.lock();
    try {
      if (!running) {
        // 위에서 확인한 뒤 종료가 시작됐다. 종료가 이 연결을 보기 전에 등록됐을 수 있으니 여기서 닫는다
        close(jobId, channel, emitter);
        return emitter;
      }
      deliver(jobId, channel, emitter);
    } catch (RuntimeException e) {
      log.warn("분석 상태 SSE 첫 전송 실패 jobId={}", jobId, e);
      emitter.completeWithError(e);
    } finally {
      channel.lock.unlock();
    }
    return emitter;
  }

  /**
   * 작업의 지금 상태를 다시 읽어, 바뀌었으면 열린 연결에 보낸다. 변경 알림을 받았을 때 부른다.
   *
   * @return 상태를 읽어 처리했으면(보낼 것이 없었거나 연결이 없었던 경우 포함) true. DB 를 못 읽었으면 false 이고, 연결은 그대로 둔다(다음 알림이나
   *     주기 맞추기가 다시 시도한다). 끊긴 연결 하나에 못 보낸 것은 실패가 아니다
   */
  public boolean refresh(UUID jobId) {
    Channel channel = channels.get(jobId);
    if (channel == null) {
      return true;
    }
    channel.lock.lock();
    try {
      deliver(jobId, channel, null);
      return true;
    } catch (RuntimeException e) {
      log.warn("분석 상태 SSE 갱신 실패 jobId={}", jobId, e);
      return false;
    } finally {
      channel.lock.unlock();
    }
  }

  /** 열린 작업 전부를 다시 읽어 보낸다. LISTEN 연결이 다시 붙었을 때(그 사이 알림을 놓쳤을 수 있다) 부른다. */
  public void refreshAll() {
    for (UUID jobId : Set.copyOf(channels.keySet())) {
      refresh(jobId);
    }
  }

  /**
   * 열린 작업들이 DB 에서 바뀌었는지 쿼리 한 번으로 보고, 바뀐 작업만 {@link #refresh}로 다시 읽어 보낸다. 변경 알림을 놓쳐도 이 주기 안에 맞춰진다.
   * 쿼리 결과는 바뀌었는지 판단에만 쓰고 보내는 상태는 잠금 안에서 새로 읽는다. 확인값은 다시 읽기에 성공했을 때만 기록한다. 실패하면 다음 주기에 다시 읽는다.
   */
  public void reconcile() {
    Set<UUID> open = Set.copyOf(channels.keySet());
    if (open.isEmpty()) {
      return;
    }
    Map<UUID, String> fingerprints = new HashMap<>();
    jdbc.query(
        "select j.id, coalesce(j.updated_at::text, '') || '|' || coalesce(g.review_status, '')"
            + " || '|' || coalesce(g.updated_at::text, '') as fingerprint"
            + " from analysis_jobs j left join guides g on g.analysis_job_id = j.id"
            + " where j.id in (:ids)",
        Map.of("ids", open),
        rs -> {
          fingerprints.put(rs.getObject("id", UUID.class), rs.getString("fingerprint"));
        });
    for (UUID jobId : open) {
      Channel channel = channels.get(jobId);
      if (channel == null) {
        continue;
      }
      String fingerprint = fingerprints.get(jobId);
      if ((fingerprint == null || !fingerprint.equals(channel.fingerprint)) && refresh(jobId)) {
        channel.fingerprint = fingerprint;
      }
    }
  }

  /** 열린 연결마다 빈 신호를 보낸다. 오가는 게 없어 중간 장비가 끊지 않게 한다. 진행했다는 뜻은 아니다. */
  public void ping() {
    for (Map.Entry<UUID, Channel> entry : Set.copyOf(channels.entrySet())) {
      Channel channel = entry.getValue();
      channel.lock.lock();
      try {
        for (SseEmitter emitter : channel.emitters) {
          try {
            emitter.send(SseEmitter.event().comment("ping"));
          } catch (IOException | IllegalStateException e) {
            remove(entry.getKey(), emitter);
          }
        }
      } finally {
        channel.lock.unlock();
      }
    }
  }

  /** 지금 열린 연결 수. */
  public int openConnections() {
    return channels.values().stream().mapToInt(c -> c.emitters.size()).sum();
  }

  /**
   * 잠금을 쥔 채 부른다. 상태를 새로 읽어 바뀌었으면 모두에게, 그대로면 새로 붙은 연결({@code newcomer})에만 보낸다. 더 바뀌지 않는 상태면 모두 닫는다.
   */
  private void deliver(UUID jobId, Channel channel, SseEmitter newcomer) {
    Optional<AnalysisJobStatusView> found = statuses.find(jobId);
    if (found.isEmpty()) {
      log.info("분석 작업이 없어 SSE 연결을 닫음 jobId={}", jobId);
      close(jobId, channel, newcomer);
      return;
    }
    AnalysisJobStatusView view = found.get();
    if (!view.equals(channel.lastSent)) {
      for (SseEmitter emitter : channel.emitters) {
        send(jobId, emitter, view);
      }
      channel.lastSent = view;
    } else if (newcomer != null) {
      send(jobId, newcomer, view);
    }
    if (view.isFinal()) {
      close(jobId, channel, newcomer);
    }
  }

  private void send(UUID jobId, SseEmitter emitter, AnalysisJobStatusView view) {
    try {
      emitter.send(
          SseEmitter.event()
              .name(EVENT)
              .data(AnalysisJobStatusResponse.from(view), MediaType.APPLICATION_JSON));
    } catch (IOException | IllegalStateException e) {
      // 끊긴 연결(브라우저가 닫힘 등). 목록에서 지운다
      remove(jobId, emitter);
    }
  }

  /**
   * 잠금을 쥔 채 부른다. 그 작업의 연결을 모두 닫고 목록에서 뺀다. 컨테이너의 완료 콜백을 기다리지 않고 바로 뺀다. 막 붙은 연결({@code newcomer})은 다른
   * 경로가 이미 목록을 비웠을 수 있어 따로 닫는다.
   */
  private void close(UUID jobId, Channel channel, SseEmitter newcomer) {
    for (SseEmitter emitter : channel.emitters) {
      emitter.complete();
    }
    if (newcomer != null) {
      newcomer.complete();
    }
    channel.emitters.clear();
    channels.remove(jobId, channel);
  }

  private void remove(UUID jobId, SseEmitter emitter) {
    channels.computeIfPresent(
        jobId,
        (id, channel) -> {
          channel.emitters.remove(emitter);
          return channel.emitters.isEmpty() ? null : channel;
        });
  }

  // --- 수명 ---

  @Override
  public void start() {
    running = true;
  }

  /** 연결을 모두 닫는다. graceful shutdown 이 진행 중인 요청을 기다리기 전에 불리도록 단계가 가장 높다. */
  @Override
  public void stop() {
    running = false;
    for (Map.Entry<UUID, Channel> entry : Set.copyOf(channels.entrySet())) {
      Channel channel = entry.getValue();
      channel.lock.lock();
      try {
        close(entry.getKey(), channel, null);
      } finally {
        channel.lock.unlock();
      }
    }
  }

  @Override
  public boolean isRunning() {
    return running;
  }

  /** 단계가 높을수록 먼저 멈춘다. 웹 서버의 graceful shutdown({@code DEFAULT_PHASE - 2048})보다 먼저 연결을 닫는다. */
  @Override
  public int getPhase() {
    return SmartLifecycle.DEFAULT_PHASE;
  }
}
