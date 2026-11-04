package com.mairor.backend.pouch.dto;

/** 등록된 항목과 등록 후 회원 파우치 버전. */
public record PouchRegistrationResponse(PouchItemResponse item, long pouchVersion) {}
