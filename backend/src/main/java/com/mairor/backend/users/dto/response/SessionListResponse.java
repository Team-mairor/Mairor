package com.mairor.backend.users.dto.response;

import java.util.List;

/** 내 로그인 기기 목록. 마지막 요청이 가장 최근인 기기가 앞에 온다. */
public record SessionListResponse(List<SessionItemResponse> items) {}
