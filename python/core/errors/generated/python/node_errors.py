from enum import Enum

class NodeErrorCode(str, Enum):
    EXECUTION_FAILED = "node.execution_failed"


NODE_MESSAGES = {
    NodeErrorCode.EXECUTION_FAILED: "Execution failed for node '{node_id}'.",
}

NODE_ERROR_IDS = {
    NodeErrorCode.EXECUTION_FAILED: "N0005",
}
