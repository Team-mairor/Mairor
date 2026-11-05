package com.mairor.backend.products.imports;

import com.mairor.backend.products.entity.ProductShade;
import org.springframework.stereotype.Component;

/**
 * 색 칸을 가리키는 곳이 아직 없을 때의 구현이다. 영상 연결(S15P31A306-324)·매칭·실행이 칸 ID 를 저장하기 시작하면 이 구현을 그 테이블을 조회하는 구현으로
 * 바꾼다. 바꾸지 않으면 참조가 있는 칸을 지울 수 있으므로, 칸 ID 를 저장하는 변경은 이 인터페이스 구현을 같이 바꿔야 한다.
 */
@Component
class NoColorReferences implements ColorReferenceChecker {

  @Override
  public boolean hasReferences(ProductShade shade) {
    return false;
  }
}
