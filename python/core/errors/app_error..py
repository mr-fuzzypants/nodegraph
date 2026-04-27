


"""
Encapsulation : each module manages its own codes and messages
Centralized formatting logic : template interpolation is in one place per module
Safe expansion : adding new modules or error types is easy
Optional central registry : you can enforce global uniqueness without coupling
Supports i18n/localization : just replace _messages with translated versions
"""

class NodeGraphError(Exception):
    def __init__(
        self,
        code,
        *,
        module_errors=None,
        metadata: dict | None = None,
        detail: str | None = None,
    ):
        self.code = code
        self.metadata = metadata or {}

        if detail is None:
            if module_errors:
                detail = module_errors.get_message(code, self.metadata)
            else:
                detail = str(code)

        self.detail = detail
        super().__init__(self.detail)

    def to_dict(self) -> dict:
        return {
            "error": self.code.value,
            "message": self.detail,
            "metadata": self.metadata,
        }


    
from enum import Enum
#from errors.registry import register_error_enum
#from errors.module import ModuleErrors

from registry import register_error_enum
from module import ModuleErrors

class NodeErrorCode(str, Enum):
    INVALID_NODE = "node.invalid"
    EXECUTION_FAILED = "node.execution_failed"

register_error_enum(NodeErrorCode)


class NodeErrorMessages(ModuleErrors):
    _messages = {
        NodeErrorCode.INVALID_NODE: "Node '{node_id}' is invalid.",
        NodeErrorCode.EXECUTION_FAILED: "Execution failed for node '{node_id}'.",
    }



class NodeNetworkErrorCode(str, Enum):
    INVALID_EXECUTION_ID = "NodeNetwork.invalid_execution_id"
    EXECUTION_FAILED = "NodeNetwork.execution_failed"

register_error_enum(NodeNetworkErrorCode)


class NodeNetworkErrorMessages(ModuleErrors):
    _messages = {
        NodeNetworkErrorCode.INVALID_EXECUTION_ID: "Invalid execution ID '{execution_id}'.",
        NodeNetworkErrorCode.EXECUTION_FAILED: "Execution failed for node '{node_id}'.",
    }



#from app_error import AppError
#from workflow.errors import WorkflowErrorCode, WorkflowErrors

try:
    raise NodeGraphError(
        NodeErrorCode.EXECUTION_FAILED,
        module_errors=NodeErrorMessages,
        metadata={"node_id": 123}
    )
except NodeGraphError as e:
    print(e.to_dict())
