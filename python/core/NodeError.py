


from enum import Enum


_registered_codes: set[str] = set()

class BaseErrorCode(str, Enum):
    def __init__(self, value: str):
        if "." not in value:
            raise ValueError(f"Error code must be namespaced: {value}")

        if value in _registered_codes:
            raise ValueError(f"Duplicate error code: {value}")

        _registered_codes.add(value)


class NodeErrorCode(BaseErrorCode):
    INVALID_NODE = "NODE_ERROR.INVALID_NODE"
    WORKFLOW_NOT_FOUND = "NODE_ERROR.WORKFLOW_NOT_FOUND {metadata: {workflow_id}}"


class WorkflowErrorCode(str, Enum):
    NOT_FOUND = "workflow.not_found"
    INVALID_STATE = "workflow.invalid_state"

ERROR_MESSAGES = {
    WorkflowErrorCode.NOT_FOUND: "Workflow '{workflow_id}' could not be found.",
    WorkflowErrorCode.INVALID_STATE: "Workflow '{workflow_id}' is in invalid state '{state}'.",
}

class AppError(Exception):
    def __init__(self, code: Enum, *, metadata: dict | None = None, detail: str | None = None):
        self.code = code
        self.metadata = metadata or {}

        # Fill in template with metadata if detail not manually provided
        if detail is None:
            template = ERROR_MESSAGES.get(code, str(code))
            try:
                detail = template.format(**self.metadata)
            except KeyError as e:
                # fallback if metadata missing
                detail = template + f" (missing key {e})"

        self.detail = detail
        super().__init__(self.detail)

    def to_dict(self):
        return {
            "error": self.code.value,
            "message": self.detail,
            "metadata": self.metadata,
        }

try:
   raise AppError(
        WorkflowErrorCode.NOT_FOUND,
        metadata={"workflow_id": 123}
    )   
except AppError as e:
    status_code = 400
    content = e.to_dict()
    print (e.detail)
    print("--")
    print(e.to_dict())