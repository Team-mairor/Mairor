package com.mairor.backend.products.event;

import java.util.Set;
import java.util.UUID;

/**
 * 서비스에 보이는 호수의 색이 바뀌었다. 카탈로그 적재가 **색을 바꾸는 같은 트랜잭션 안에서 동기로** 발행한다.
 *
 * <p>"보이는 색"은 사용할 수 있는 색 칸의 HEX 다. 색을 저장했지만 사용 불가({@code BELOW_THRESHOLD})라 서비스 응답이 그대로인 변경은 이 이벤트의
 * 대상이 아니다. 사용 중이던 색을 사용 불가로 내리거나 사용할 수 있는 칸을 지우는 것은 보이는 색이 바뀐 것이다.
 *
 * <p>같은 트랜잭션에서 동기로 도는 리스너는 바뀐 색과 같은 시점에 자기 데이터를 고칠 수 있다(파우치 회원 버전, 가이드 기준 버전). 리스너가 예외를 던지면 색 변경도
 * 함께 롤백되므로, 리스너는 가볍고 같은 DB 안에서 끝나는 일만 해야 한다.
 *
 * @param shadeIds 색이 바뀐 호수. 비어 있지 않다
 */
public record CatalogColorChanged(Set<UUID> shadeIds) {

  public CatalogColorChanged {
    if (shadeIds == null || shadeIds.isEmpty()) {
      throw new IllegalArgumentException("shadeIds 는 비어 있을 수 없다");
    }
    shadeIds = Set.copyOf(shadeIds);
  }
}
