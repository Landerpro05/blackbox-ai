from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator


def ensure_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


UTCDatetime = Annotated[datetime, AfterValidator(ensure_utc)]
