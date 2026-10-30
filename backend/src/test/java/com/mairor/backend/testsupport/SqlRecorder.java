package com.mairor.backend.testsupport;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import javax.sql.DataSource;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

/**
 * 테스트 중 DB 로 나간 SQL 문장을 순서대로 기록한다. 세션 저장소가 요청 한 건에 몇 번, 언제 쓰는지 세는 데 쓴다.
 *
 * <p>{@code DataSource} 를 JDK 동적 프록시로 감싸 {@code prepareStatement}/{@code createStatement} 가 돌려준 문장이
 * 실행될 때 기록한다. 의존성은 더하지 않는다. 한 문장은 {@code "UPDATE spring_session"} 처럼 "동사 + 테이블"로 줄여 남기고, 배치는 한 번
 * 실행에 한 건으로 센다. 이 클래스를 가져오는 테스트({@link Config})에서만 켜진다.
 */
public final class SqlRecorder {

  private static final Pattern TABLE =
      Pattern.compile("(?i)\\b(?:from|into|update)\\s+(?:only\\s+)?([a-z0-9_.\"]+)");
  private static final Set<String> EXECUTE_METHODS =
      Set.of(
          "execute",
          "executeUpdate",
          "executeLargeUpdate",
          "executeQuery",
          "executeBatch",
          "executeLargeBatch");
  private static final Set<String> WRITE_VERBS = Set.of("INSERT", "UPDATE", "DELETE");

  private final List<String> statements = new CopyOnWriteArrayList<>();

  public void clear() {
    statements.clear();
  }

  /** 기록된 모든 문장(실행 순서). */
  public List<String> all() {
    return List.copyOf(statements);
  }

  /** 세션 저장소({@code spring_session*})에 쓴 문장만. */
  public List<String> sessionWrites() {
    return statements.stream().filter(SqlRecorder::isSessionWrite).toList();
  }

  private static boolean isSessionWrite(String statement) {
    int space = statement.indexOf(' ');
    return space > 0
        && WRITE_VERBS.contains(statement.substring(0, space))
        && statement
            .substring(space + 1)
            .toLowerCase(java.util.Locale.ROOT)
            .startsWith("spring_session");
  }

  private void record(String sql) {
    String verb = sql.strip().split("\\s+", 2)[0].toUpperCase(java.util.Locale.ROOT);
    Matcher table = TABLE.matcher(sql);
    String name = table.find() ? table.group(1).replace("\"", "") : "?";
    statements.add(verb + " " + name);
  }

  DataSource wrap(DataSource target) {
    return (DataSource)
        Proxy.newProxyInstance(
            SqlRecorder.class.getClassLoader(),
            new Class<?>[] {DataSource.class},
            (proxy, method, args) -> {
              Object result = invoke(target, method, args);
              return "getConnection".equals(method.getName()) ? wrap((Connection) result) : result;
            });
  }

  private Connection wrap(Connection target) {
    return (Connection)
        Proxy.newProxyInstance(
            SqlRecorder.class.getClassLoader(),
            new Class<?>[] {Connection.class},
            (proxy, method, args) -> {
              Object result = invoke(target, method, args);
              if ("prepareStatement".equals(method.getName())
                  && args != null
                  && args[0] instanceof String sql) {
                return wrap((PreparedStatement) result, sql);
              }
              if ("createStatement".equals(method.getName())) {
                return wrap((Statement) result);
              }
              return result;
            });
  }

  private PreparedStatement wrap(PreparedStatement target, String sql) {
    return (PreparedStatement)
        Proxy.newProxyInstance(
            SqlRecorder.class.getClassLoader(),
            new Class<?>[] {PreparedStatement.class},
            (proxy, method, args) -> {
              if (EXECUTE_METHODS.contains(method.getName())) {
                record(sql);
              }
              return invoke(target, method, args);
            });
  }

  private Statement wrap(Statement target) {
    return (Statement)
        Proxy.newProxyInstance(
            SqlRecorder.class.getClassLoader(),
            new Class<?>[] {Statement.class},
            (proxy, method, args) -> {
              if (EXECUTE_METHODS.contains(method.getName())
                  && args != null
                  && args.length > 0
                  && args[0] instanceof String sql) {
                record(sql);
              }
              return invoke(target, method, args);
            });
  }

  private static Object invoke(Object target, java.lang.reflect.Method method, Object[] args)
      throws Throwable {
    try {
      return method.invoke(target, args);
    } catch (InvocationTargetException e) {
      throw e.getCause();
    }
  }

  /** 이 설정을 {@code @Import} 한 테스트에서만 DataSource 를 감싼다. */
  @TestConfiguration(proxyBeanMethods = false)
  public static class Config {

    @Bean
    SqlRecorder sqlRecorder() {
      return new SqlRecorder();
    }

    @Bean
    static BeanPostProcessor recordingDataSourcePostProcessor(
        ObjectProvider<SqlRecorder> recorder) {
      return new BeanPostProcessor() {
        @Override
        public Object postProcessAfterInitialization(Object bean, String beanName) {
          if (bean instanceof DataSource dataSource && !Proxy.isProxyClass(bean.getClass())) {
            return recorder.getObject().wrap(dataSource);
          }
          return bean;
        }
      };
    }
  }
}
