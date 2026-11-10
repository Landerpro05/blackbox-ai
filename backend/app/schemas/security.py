from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator

from app.schemas.projects import ProjectName

Role = Literal["owner", "admin", "member", "viewer"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(Input):
    email: Annotated[EmailStr, Field(max_length=254)]
    password: SecretStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize(cls, value):
        return value.strip().casefold() if isinstance(value, str) else value

    @field_validator("password")
    @classmethod
    def bounded(cls, value):
        if not 1 <= len(value.get_secret_value()) <= 128:
            raise ValueError("Contraseña fuera de los límites permitidos.")
        return value


class Register(Credentials):
    invitation: Annotated[str, Field(min_length=32, max_length=128)]
    workspace_name: ProjectName = "Mi workspace"


class ChangePassword(Input):
    current_password: SecretStr
    new_password: SecretStr

    @field_validator("current_password", "new_password")
    @classmethod
    def bounded(cls, value):
        if not 1 <= len(value.get_secret_value()) <= 128:
            raise ValueError("Contraseña fuera de los límites permitidos.")
        return value


class WorkspaceInput(Input):
    name: ProjectName


class WorkspaceSelection(Input):
    workspace_id: Annotated[
        str, Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9-]+$")
    ]


class MemberRole(Input):
    role: Role


class InviteInput(Input):
    email: Annotated[EmailStr, Field(max_length=254)]
    role: Literal["admin", "member", "viewer"] = "member"

    _email = field_validator("email", mode="before")(Credentials.normalize.__func__)


class AcceptInvite(Input):
    invitation: Annotated[str, Field(min_length=32, max_length=128)]
