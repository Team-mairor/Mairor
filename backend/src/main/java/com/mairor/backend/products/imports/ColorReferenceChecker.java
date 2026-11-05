package com.mairor.backend.products.imports;

import com.mairor.backend.products.entity.ProductShade;

/**
 * 호수의 색 칸을 가리키는 참조가 있는지 확인한다. 참조는 영상 연결의 쓴 칸, 저장된 매칭 후보의 선택 칸, 실행·리포트의 선택 칸(스냅샷에 남은 {@code colorId}
 * 포함)이다. 참조가 있는 칸은 이름·번호 근거가 아니면 어떤 경우에도 바꾸지 않는다.
 *
 * <p>확인과 교체는 같은 트랜잭션에서 하고, 교체하는 쪽이 호수 행을 쓰기 잠금으로 잡아 그 사이 새 참조가 생기지 않게 한다(적재 단계의 책임).
 */
public interface ColorReferenceChecker {

  boolean hasReferences(ProductShade shade);
}
