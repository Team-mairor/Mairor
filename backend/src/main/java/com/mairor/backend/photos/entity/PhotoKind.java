package com.mairor.backend.photos.entity;

/** 저장하는 사진의 용도. PHOTO_BOOTH 사진은 만료되는 공유 링크로만 공개된다. */
public enum PhotoKind {
  FACE_REGISTRATION,
  STEP,
  PHOTO_BOOTH
}
