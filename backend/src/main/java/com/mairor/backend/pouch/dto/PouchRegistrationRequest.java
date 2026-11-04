package com.mairor.backend.pouch.dto;

import com.mairor.backend.pouch.entity.RegistrationMode;
import java.util.UUID;

/** POST 파우치 등록 요청. CATALOG 는 식별자, MANUAL 은 직접 입력값을 보낸다. */
public record PouchRegistrationRequest(
    RegistrationMode registrationMode,
    UUID productId,
    UUID shadeId,
    String category,
    String type,
    String brand,
    String name,
    String shadeName,
    String colorHex) {}
