package com.mairor.backend.common.security;

/**
 * 저장소에 있는 세션 값을 읽어 내지 못했다(역직렬화 실패). 값이 깨졌거나, 배포로 클래스 구조가 바뀌어 옛 세션을 더 이상 읽을 수 없을 때 생긴다. 사용자의 세션이 못
 * 쓰게 된 것이라 다시 로그인하게 하면 된다.
 *
 * <p>새 값을 저장하지 못하는 실패(직렬화 실패)와 구분하려고 둔 예외다. 둘은 Spring 에서 같은 예외 종류로 나오지만 뜻이 다르다. 직렬화 실패는 직렬화할 수 없는
 * 값을 세션에 넣은 서버 버그라서 사용자에게 "로그인 만료"로 보이면 안 된다. 직렬화 경계({@link SessionSerializerConfig})에서 읽는 쪽만 이 예외로
 * 감싼다.
 */
public class UnreadableSessionException extends RuntimeException {

  public UnreadableSessionException(String message, Throwable cause) {
    super(message, cause);
  }
}
