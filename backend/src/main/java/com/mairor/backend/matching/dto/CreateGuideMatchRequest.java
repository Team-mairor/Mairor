package com.mairor.backend.matching.dto;

import jakarta.validation.constraints.NotNull;
import java.util.UUID;

public record CreateGuideMatchRequest(@NotNull UUID guideId) {}
