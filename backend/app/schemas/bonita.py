from typing import Any

from pydantic import BaseModel


class BonitaTestVariablesRequest(BaseModel):
    case_id: int
    variables: dict[str, Any]
