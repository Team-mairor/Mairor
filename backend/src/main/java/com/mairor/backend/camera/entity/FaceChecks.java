package com.mairor.backend.camera.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import lombok.Getter;

/** 클라이언트가 판정한 촬영 조건. 서버 얼굴 인식 결과로 해석하지 않는다. */
@Getter
@Embeddable
public class FaceChecks {
  @Column(nullable = false)
  private boolean lighting;

  @Column(nullable = false)
  private boolean distance;

  @Column(nullable = false)
  private boolean frontal;

  @Column(nullable = false)
  private boolean unobstructed;

  @Column(name = "makeup_detected", nullable = false)
  private boolean makeupDetected;

  protected FaceChecks() {}

  public FaceChecks(
      boolean lighting,
      boolean distance,
      boolean frontal,
      boolean unobstructed,
      boolean makeupDetected) {
    if (!lighting || !distance || !frontal || !unobstructed) {
      throw new IllegalArgumentException("필수 촬영 조건을 모두 만족해야 한다");
    }
    this.lighting = lighting;
    this.distance = distance;
    this.frontal = frontal;
    this.unobstructed = unobstructed;
    this.makeupDetected = makeupDetected;
  }
}
