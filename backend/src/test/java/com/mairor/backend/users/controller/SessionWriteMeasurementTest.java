package com.mairor.backend.users.controller;

import static org.assertj.core.api.Assertions.assertThat;

import com.mairor.backend.TestcontainersConfiguration;
import com.mairor.backend.testsupport.AuthFlowClient;
import com.mairor.backend.testsupport.AuthFlowClient.Account;
import com.mairor.backend.testsupport.AuthFlowClient.Login;
import com.mairor.backend.testsupport.SessionTestClient;
import com.mairor.backend.testsupport.SqlRecorder;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;
import org.springframework.core.env.Environment;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * 요청 한 건이 세션 저장소({@code spring_session*})에 몇 번, 어떤 순서로 쓰는지 센다. 세션을 응답 커밋 때 저장하는지({@code on_save})
 * 만들자마자 저장하는지({@code immediate}) 바꿀 때 쓰기 횟수와 시점이 어떻게 달라지는지 확인한다.
 *
 * <p>결과는 {@code build/session-write-measurement-<저장 방식>.txt} 에 남기고, 인증된 일반 요청이 세션 쓰기를 한 건(마지막 접근 시각
 * 갱신) 넘기지 않는다는 것만 확인한다. 로그인과 로그아웃의 쓰기 횟수는 저장 방식에 따라 달라서 단정하지 않는다.
 */
@Import({TestcontainersConfiguration.class, SqlRecorder.Config.class})
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SessionWriteMeasurementTest {

  @LocalServerPort private int port;
  @Autowired private SqlRecorder recorder;
  @Autowired private JdbcTemplate jdbc;
  @Autowired private Environment environment;

  private AuthFlowClient flow;
  private final List<String> report = new ArrayList<>();

  @BeforeEach
  void setUp() {
    flow = new AuthFlowClient(new SessionTestClient(port));
    jdbc.update("delete from spring_session");
  }

  @Test
  void measuresSessionWritesPerRequestKind() throws Exception {
    Account account = flow.signUp();

    recorder.clear();
    flow.loginRaw(account.email(), "WrongPassw0rd!", AuthFlowClient.CHROME_WINDOWS);
    note("로그인 실패(세션 없음)");

    recorder.clear();
    Login login = flow.login(account, AuthFlowClient.CHROME_WINDOWS);
    note("로그인 성공(새 세션)");

    recorder.clear();
    assertThat(flow.me(login.cookie()).status()).isEqualTo(200);
    int firstMe = recorder.sessionWrites().size();
    note("인증된 GET /me (1번째)");

    recorder.clear();
    assertThat(flow.me(login.cookie()).status()).isEqualTo(200);
    int secondMe = recorder.sessionWrites().size();
    note("인증된 GET /me (2번째)");

    recorder.clear();
    assertThat(flow.logout(login.cookie(), login.csrfToken()).status()).isEqualTo(204);
    note("로그아웃");

    String mode = environment.getProperty("spring.session.jdbc.flush-mode", "on_save(기본값)");
    Files.writeString(
        Path.of("build/session-write-measurement-" + mode.replaceAll("[^a-z_]", "") + ".txt"),
        "flush-mode="
            + mode
            + System.lineSeparator()
            + String.join(System.lineSeparator(), report));

    // 인증된 일반 요청은 세션 쓰기를 한 건(마지막 접근 시각 갱신) 넘기지 않는다
    assertThat(firstMe).isLessThanOrEqualTo(1);
    assertThat(secondMe).isLessThanOrEqualTo(1);
  }

  private void note(String label) {
    report.add(
        label
            + "\n  세션 쓰기 "
            + recorder.sessionWrites().size()
            + "건: "
            + recorder.sessionWrites()
            + "\n  전체 문장 순서: "
            + recorder.all());
  }
}
