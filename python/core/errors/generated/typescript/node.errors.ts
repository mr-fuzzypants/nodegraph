export type NodeError =
  | {
      id: "N0005";
      code: "node.execution_failed";
      metadata: { node_id: string; };
    }
;

export function formatNodeError(error: NodeError): string {
  switch (error.code) {
    case "node.execution_failed":
      return `Execution failed for node '${error.metadata.node_id}'. (Error N0005)`;
  }
}