from enum import Enum

class WorkflowErrorCode(str, Enum):
    NOT_FOUND = "workflow.not_found"
    INVALID_STATE = "workflow.invalid_state"


WORKFLOW_MESSAGES = {
    WorkflowErrorCode.NOT_FOUND: "Workflow '{workflow_id}' could not be found.",
    WorkflowErrorCode.INVALID_STATE: "Workflow '{workflow_id}' is in invalid state '{state}'.",
}

WORKFLOW_ERROR_IDS = {
    WorkflowErrorCode.NOT_FOUND: "W0001",
    WorkflowErrorCode.INVALID_STATE: "W0002",
}
