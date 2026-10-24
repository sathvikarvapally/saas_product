from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class InputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OutputSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
