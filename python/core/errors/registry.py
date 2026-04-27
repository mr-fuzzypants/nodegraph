from enum import Enum

_registered_codes: set[str] = set()

def register_error_enum(enum_cls: type[Enum]) -> None:
    for member in enum_cls:
        value = member.value

        if "." not in value:
            raise ValueError(
                f"Error code must be namespaced: {value}"
            )

        if value in _registered_codes:
            raise ValueError(
                f"Duplicate error code detected: {value}"
            )

        _registered_codes.add(value)
        