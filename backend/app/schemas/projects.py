import re
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    HttpUrl,
    StringConstraints,
    model_validator,
)

from app.schemas.common import UTCDatetime


def clean_name(value: str) -> str:
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("El nombre no puede contener caracteres de control.")
    return value


ProjectName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
    AfterValidator(clean_name),
]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]


def validate_base_url(value: object) -> str:
    """Syntax only. No DNS, sockets, HTTP calls or browser operations."""
    if not isinstance(value, str):
        raise ValueError("Introduce una URL HTTP o HTTPS absoluta.")
    value = value.strip()
    if not re.match(r"^https?://", value, flags=re.IGNORECASE):
        raise ValueError("La URL debe empezar por http:// o https://.")
    if (
        len(value) > 2048
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)
        or "\\" in value
    ):
        raise ValueError(
            "La URL no puede contener espacios, barras inversas ni superar 2048 caracteres."
        )
    url = HttpUrl(value)
    if (
        url.username is not None
        or url.password is not None
        or url.query is not None
        or url.fragment is not None
    ):
        raise ValueError(
            "La URL base no puede contener credenciales, parámetros ni fragmentos."
        )
    normalized = str(url)
    if len(normalized) > 2048:
        raise ValueError("La URL normalizada supera 2048 caracteres.")
    return normalized


BaseUrl = Annotated[str, BeforeValidator(validate_base_url)]


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ProjectName
    description: Description = ""
    base_url: BaseUrl


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ProjectName | None = None
    description: Description | None = None
    base_url: BaseUrl | None = None

    @model_validator(mode="after")
    def require_non_null_changes(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Envía al menos un campo para actualizar.")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Los campos enviados no pueden ser nulos.")
        return self


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    base_url: str
    max_pages: int
    max_depth: int
    max_duration_seconds: int
    created_at: UTCDatetime
    updated_at: UTCDatetime


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    total: int
    limit: int
    offset: int
