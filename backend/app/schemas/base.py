from pydantic import BaseModel, ConfigDict

from app.schemas.utils import to_camel_case


class CamelInBaseModel(BaseModel):
    # Requests: only accept camelCase.
    # Set validate_by_name=False to prevent snake_case input.
    # Set from_attributes=False to prevent ORM input.
    model_config = ConfigDict(
        alias_generator=to_camel_case, validate_by_name=False, from_attributes=False
    )


class CamelOutBaseModel(BaseModel):
    # Responses: read from ORM attributes (snake_case).
    # Set validate_by_name=True to allow snake_case input.
    # Set from_attributes=True to allow ORM input.
    model_config = ConfigDict(
        alias_generator=to_camel_case, validate_by_name=True, from_attributes=True
    )
