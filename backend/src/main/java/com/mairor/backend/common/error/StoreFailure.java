package com.mairor.backend.common.error;

import java.sql.SQLException;
import java.sql.SQLNonTransientConnectionException;
import java.sql.SQLTransientConnectionException;
import org.hibernate.TransactionException;
import org.hibernate.exception.JDBCConnectionException;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.transaction.CannotCreateTransactionException;

/**
 * 저장소(DB) 예외가 "잠시 후 다시 시도하면 될 수 있는 장애"인지 가리는 기준. 컨트롤러 안에서 나는 예외({@link GlobalExceptionHandler})와 필터
 * 단계에서 나는 예외({@code SessionStoreFailureFilter})가 같은 함수를 써서 같은 원인이 어디서 나든 같은 응답(503)이 나가게 한다.
 *
 * <p>예외 하나의 타입이 아니라 <b>원인 사슬 전체</b>를 본다. 연결이 죽은 상태에서 쿼리가 실패하고 롤백까지 실패하면 스프링은 원래 예외를 롤백 예외로 덮어쓰고,
 * 던져지는 것은 "롤백할 수 없다"는 예외뿐이기 때문이다.
 *
 * <p>장애로 보는 것(503):
 *
 * <ul>
 *   <li>연결 실패({@link DataAccessResourceFailureException}), 일시적 장애({@link
 *       TransientDataAccessException}: 쿼리 시간 초과, 락 경합 등)
 *   <li>트랜잭션을 열지 못함({@link CannotCreateTransactionException}: 연결 풀이 바닥나 연결을 얻지 못한 경우 포함)
 *   <li>트랜잭션의 롤백·커밋 자체가 실패({@link TransactionException}), 하이버네이트의 연결 실패({@link
 *       JDBCConnectionException}). 롤백이 실패하는 것은 연결이 죽었다는 뜻이다
 *   <li>JDBC 표준의 연결 오류({@link SQLTransientConnectionException}, {@link
 *       SQLNonTransientConnectionException}), 또는 SQLSTATE 가 연결 오류 부류({@code 08})인 {@link
 *       SQLException}
 * </ul>
 *
 * <p>장애로 보지 <b>않는 것</b>(500): 잘못된 SQL, 스키마 불일치, 제약 위반 같은 서버 문제. 해석되지 않은 원시 {@link SQLException} 도
 * 장애로 단정하지 않는다.
 */
public final class StoreFailure {

  /** 순환하는 원인 사슬에서 벗어나기 위한 상한. */
  private static final int MAX_DEPTH = 32;

  private StoreFailure() {}

  public static boolean isUnavailable(Throwable e) {
    Throwable t = e;
    for (int depth = 0; t != null && depth < MAX_DEPTH; depth++) {
      if (isUnavailableType(t)) {
        return true;
      }
      Throwable cause = t.getCause();
      t = cause == t ? null : cause;
    }
    return false;
  }

  private static boolean isUnavailableType(Throwable t) {
    if (t instanceof DataAccessResourceFailureException
        || t instanceof TransientDataAccessException
        || t instanceof CannotCreateTransactionException
        || t instanceof TransactionException
        || t instanceof JDBCConnectionException
        || t instanceof SQLTransientConnectionException
        || t instanceof SQLNonTransientConnectionException) {
      return true;
    }
    return t instanceof SQLException sql
        && sql.getSQLState() != null
        && sql.getSQLState().startsWith("08");
  }
}
