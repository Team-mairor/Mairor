package com.mairor.backend.pouch.dto;

public record PouchUpdateResponse(PouchItemResponse item, long pouchVersion) {}
