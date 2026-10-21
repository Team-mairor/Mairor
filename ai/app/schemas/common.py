from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ErrorDetail(CamelModel):
    field: str
    reason: str


class ErrorResponse(CamelModel):
    code: str
    message: str
    details: list[ErrorDetail] | None = None
