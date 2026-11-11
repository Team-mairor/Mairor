package com.mairor.backend.executions.dto;

import jakarta.validation.constraints.NotNull;

public record PhotoConsentRequest(@NotNull Boolean enabled) {}
