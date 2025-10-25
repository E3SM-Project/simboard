import re


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

    return parts[0].lower() + "".join(p.title() for p in parts[1:])


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
    snake_with_caps = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", camel_str)

    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", snake_with_caps).lower()
