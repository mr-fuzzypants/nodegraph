export type WorkflowError =
  | {
      id: "W0001";
      code: "workflow.not_found";
      metadata: { workflow_id: number; };
    }
  | {
      id: "W0002";
      code: "workflow.invalid_state";
      metadata: { workflow_id: number; state: string; };
    }
;

export function formatWorkflowError(error: WorkflowError): string {
  switch (error.code) {
    case "workflow.not_found":
      return `Workflow '${error.metadata.workflow_id}' could not be found. (Error W0001)`;
    case "workflow.invalid_state":
      return `Workflow '${error.metadata.workflow_id}' is in invalid state '${error.metadata.state}'. (Error W0002)`;
  }
}