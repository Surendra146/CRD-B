from typing import Any

from pydantic import BaseModel, ConfigDict


class PayloadSchema(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_unset=True)
