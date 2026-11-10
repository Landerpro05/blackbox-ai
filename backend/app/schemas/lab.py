import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from app.schemas.projects import BaseUrl, Description, ProjectName
from app.schemas.runs import RunLimits
from app.testing.local_policy import local_origin
from app.testing.policy import DemoPolicy


def relative_path(value: str) -> str:
    if not re.fullmatch(r"/[A-Za-z0-9_/-]*", value) or "//" in value or ".." in value:
        raise ValueError(
            "Usa una ruta relativa segura, sin consultas, fragmentos ni codificación."
        )
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EnvironmentInput(StrictModel):
    name: ProjectName
    kind: Literal["demo", "local"]
    base_url: BaseUrl
    limits: RunLimits = Field(default_factory=RunLimits)

    @model_validator(mode="after")
    def destination(self):
        if self.kind == "demo":
            DemoPolicy().authorize(self.base_url)
        else:
            local_origin(self.base_url)
        return self


class SuiteInput(StrictModel):
    name: ProjectName
    description: Description = ""


class BaseCase(StrictModel):
    path: Annotated[str, Field(max_length=512)] = "/"
    _path = field_validator("path")(relative_path)


class HTTPCase(BaseCase):
    type: Literal["http_status"]
    minimum: Annotated[StrictInt, Field(ge=100, le=599)] = 200
    maximum: Annotated[StrictInt, Field(ge=100, le=599)] = 200

    @model_validator(mode="after")
    def ordered(self):
        if self.minimum > self.maximum:
            raise ValueError("El rango HTTP no es válido.")
        return self


class TitleCase(BaseCase):
    type: Literal["title"]
    expected_title: Annotated[str, Field(min_length=1, max_length=200)]


class ElementCase(BaseCase):
    type: Literal["element_exists"]
    selector: Annotated[str, Field(min_length=1, max_length=100)]

    @field_validator("selector")
    @classmethod
    def simple_css(cls, value):
        if not re.fullmatch(
            r'(?:[a-zA-Z][a-zA-Z0-9_-]*|[.#][a-zA-Z_][a-zA-Z0-9_-]*|\[data-testid="[a-zA-Z0-9_-]+"\])',
            value,
        ):
            raise ValueError('Usa un tag, #id, .clase o [data-testid="valor"].')
        return value


class TextCase(BaseCase):
    type: Literal["text_visible"]
    text: Annotated[str, Field(min_length=1, max_length=300)]


class JSCase(BaseCase):
    type: Literal["no_js_errors"]


class LinksCase(BaseCase):
    type: Literal["internal_links"]


class NavigationCase(BaseCase):
    type: Literal["navigate"]
    destination: Annotated[str, Field(max_length=512)]
    _destination = field_validator("destination")(relative_path)


Definition = Annotated[
    HTTPCase | TitleCase | ElementCase | TextCase | JSCase | LinksCase | NavigationCase,
    Field(discriminator="type"),
]


class CaseInput(StrictModel):
    name: ProjectName
    position: Annotated[StrictInt, Field(ge=0, le=99)]
    enabled: StrictBool = True
    definition: Definition


class SuiteRunCreate(StrictModel):
    environment_id: UUID
    authorize: StrictBool
    consent_origin: Annotated[str, Field(max_length=200)]


class AvailabilityRequest(StrictModel):
    authorize: StrictBool
    consent_origin: Annotated[str, Field(max_length=200)]


class SuggestionImport(StrictModel):
    analysis_id: UUID
    suggestion_index: Annotated[StrictInt, Field(ge=0, le=7)]
    name: ProjectName
    position: Annotated[StrictInt, Field(ge=0, le=99)]
    confirm: StrictBool


class Patch(StrictModel):
    @model_validator(mode="after")
    def changes(self):
        if not self.model_fields_set or any(
            getattr(self, key) is None for key in self.model_fields_set
        ):
            raise ValueError("Envía campos no nulos para actualizar.")
        return self


class EnvironmentPatch(Patch):
    name: ProjectName | None = None
    kind: Literal["demo", "local"] | None = None
    base_url: BaseUrl | None = None
    limits: RunLimits | None = None


class SuitePatch(Patch):
    name: ProjectName | None = None
    description: Description | None = None


class CasePatch(Patch):
    name: ProjectName | None = None
    position: Annotated[StrictInt | None, Field(ge=0, le=99)] = None
    enabled: StrictBool | None = None
    definition: Definition | None = None
