import re

from pydantic import BaseModel, ConfigDict


def to_camel_case(string: str) -> str:
    """Convert a snake_case string to camelCase.

    This function is particularly useful when working with Pydantic models,
    where you may want to transform field names from Python's snake_case
    convention to camelCase for JSON serialization. For example, APIs often
    use camelCase for field names in their payloads, and this function can
    be used to customize the `alias_generator` in Pydantic schemas.

    Parameters
    ----------
    string : str
        The input string in snake_case format.

    Returns
    -------
    str
        The converted string in camelCase format.

    Examples
    --------
    >>> to_camel_case("example_string")
    'exampleString'
    >>> to_camel_case("another_example")
    'anotherExample'

    Usage in Pydantic
    -----------------
    You can use this function as the `alias_generator` in a Pydantic model
    to automatically convert field names to camelCase during JSON serialization:

    >>> from pydantic import BaseModel
    >>> class ExampleModel(BaseModel):
    ...     example_field: str
    ...     another_field: int
    ...
    ...     class Config:
    ...         alias_generator = to_camel_case
    ...         allow_population_by_field_name = True
    >>> model = ExampleModel(example_field="value", another_field=42)
    >>> model.dict(by_alias=True)
    {'exampleField': 'value', 'anotherField': 42}
    """
    parts = string.split("_")

    return parts[0] + "".join(p.title() for p in parts[1:])


def to_snake_case(camel_str: str) -> str:
    """
    Convert a CamelCase string to snake_case.

    Parameters
    ----------
    camel_str : str
        The input string in CamelCase format.

    Returns
    -------
    str
        The converted string in snake_case format.
    """
    return re.sub(r"([A-Z])", r"_\1", camel_str).lower().lstrip("_")


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
