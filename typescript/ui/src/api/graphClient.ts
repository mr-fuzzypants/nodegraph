import axios from 'axios';
import type {
  SerializedNetwork,
  NetworkListItem,
} from '../types/uiTypes';
import { useInfoLogStore } from '../store/infoLogStore';

const BASE = '/api';
const api = axios.create({ baseURL: BASE });

function requestLabel(config: any): string {
  const method = (config.method ?? 'get').toUpperCase();
  const url = `${config.baseURL ?? ''}${config.url ?? ''}`;
  return `${method} ${url}`;
}

function logApi(status: 'pending' | 'success' | 'error', message: string) {
  useInfoLogStore.getState().addEntry({ kind: 'api', status, message });
}

api.interceptors.request.use((config) => {
  (config as any).metadata = { startedAt: performance.now() };
  logApi('pending', `-> ${requestLabel(config)}`);
  return config;
});

api.interceptors.response.use(
  (response) => {
    const startedAt = (response.config as any).metadata?.startedAt;
    const elapsed = typeof startedAt === 'number'
      ? ` ${Math.round(performance.now() - startedAt)}ms`
      : '';
    logApi('success', `<- ${response.status} ${requestLabel(response.config)}${elapsed}`);
    return response;
  },
  (error) => {
    const config = error.config ?? {};
    const startedAt = config.metadata?.startedAt;
    const elapsed = typeof startedAt === 'number'
      ? ` ${Math.round(performance.now() - startedAt)}ms`
      : '';
    const status = error.response?.status ?? 'ERR';
    const detail = error.message ? ` (${error.message})` : '';
    logApi('error', `<- ${status} ${requestLabel(config)}${elapsed}${detail}`);
    return Promise.reject(error);
  },
);

export const graphClient = {
  /** Get the root network id */
  getRootNetwork(): Promise<{ id: string; name: string }> {
    return api.get('/networks/root').then((r) => r.data);
  },

  /** List all networks */
  listNetworks(): Promise<NetworkListItem[]> {
    return api.get('/networks').then((r) => r.data);
  },

  /** Save selected nodes from a network to a server-side graph JSON file. */
  saveSelection(
    name: string,
    networkId: string,
    nodeIds: string[],
  ): Promise<{ ok: true; name: string; path: string }> {
    return api.post('/graphs/selection', { name, networkId, nodeIds }).then((r) => r.data);
  },

  /** Fetch a network's full graph */
  getNetwork(id: string): Promise<SerializedNetwork> {
    return api.get(`/networks/${id}`).then((r) => r.data);
  },

  /** Create a subnetwork inside `parentId` */
  createSubnetwork(parentId: string, name: string): Promise<{ id: string; name: string }> {
    return api.post(`/networks/${parentId}/networks`, { name }).then((r) => r.data);
  },

  /** Move existing nodes into a new subnetwork and rewire boundary ports. */
  groupNodes(networkId: string, nodeIds: string[], name = ''): Promise<SerializedNetwork> {
    return api.post(`/networks/${networkId}/group-nodes`, { nodeIds, name }).then((r) => r.data);
  },

  /** Create a node inside `networkId` */
  createNode(
    networkId: string,
    type: string,
    name: string,
    position?: { x: number; y: number },
  ): Promise<{ id: string; name: string; type: string }> {
    return api.post(`/networks/${networkId}/nodes`, { type, name, position }).then((r) => r.data);
  },

  /** Delete a node */
  deleteNode(networkId: string, nodeId: string): Promise<void> {
    return api.delete(`/networks/${networkId}/nodes/${nodeId}`).then(() => undefined);
  },

  /** Rename a node */
  renameNode(networkId: string, nodeId: string, name: string): Promise<void> {
    return api.put(`/networks/${networkId}/nodes/${nodeId}/name`, { name }).then(() => undefined);
  },

  /** Add an edge between two ports */
  addEdge(
    networkId: string,
    sourceNodeId: string,
    sourcePort: string,
    targetNodeId: string,
    targetPort: string,
  ): Promise<SerializedNetwork> {
    return api
      .post(`/networks/${networkId}/edges`, {
        sourceNodeId,
        sourcePort,
        targetNodeId,
        targetPort,
      })
      .then((r) => r.data);
  },

  /** Remove an edge */
  removeEdge(
    networkId: string,
    sourceNodeId: string,
    sourcePort: string,
    targetNodeId: string,
    targetPort: string,
  ): Promise<void> {
    return api
      .delete(`/networks/${networkId}/edges`, {
        data: { sourceNodeId, sourcePort, targetNodeId, targetPort },
      })
      .then(() => undefined);
  },

  /** Persist a node's layout position */
  setPosition(networkId: string, nodeId: string, x: number, y: number): Promise<void> {
    return api
      .put(`/networks/${networkId}/nodes/${nodeId}/position`, { x, y })
      .then(() => undefined);
  },

  /** Set a port value directly */
  setPortValue(
    networkId: string,
    nodeId: string,
    portName: string,
    value: any,
  ): Promise<void> {
    return api
      .put(`/networks/${networkId}/nodes/${nodeId}/ports/${portName}`, { value })
      .then(() => undefined);
  },

  /** Add a dynamic input port to a node that supports it. */
  addDynamicInputPort(
    networkId: string,
    nodeId: string,
    name: string,
    valueType: string,
  ): Promise<SerializedNetwork> {
    return api
      .post(`/networks/${networkId}/nodes/${nodeId}/input-ports`, { name, valueType })
      .then((r) => r.data);
  },

  /** Remove a dynamic input port from a node that supports it. */
  removeDynamicInputPort(
    networkId: string,
    nodeId: string,
    portName: string,
  ): Promise<void> {
    return api
      .delete(`/networks/${networkId}/nodes/${nodeId}/input-ports/${portName}`)
      .then(() => undefined);
  },

  /** Add a tunnel input or output port to a subnetwork */
  addTunnelPort(
    networkId: string,
    name: string,
    direction: 'input' | 'output',
    portFunction: 'DATA' | 'CONTROL' = 'DATA',
    valueType = 'ANY',
  ): Promise<SerializedNetwork> {
    return api
      .post(`/networks/${networkId}/tunnel-ports`, {
        name,
        direction,
        function: portFunction,
        valueType,
      })
      .then((r) => r.data);
  },

  /** Create a tunnel input port from an existing source port and connect it. */
  connectToNewTunnelInput(
    networkId: string,
    sourceNodeId: string,
    sourcePort: string,
  ): Promise<SerializedNetwork> {
    return api
      .post(`/networks/${networkId}/tunnel-input-connections`, { sourceNodeId, sourcePort })
      .then((r) => r.data);
  },

  /** Create a tunnel input port for an existing target port and connect it. */
  connectNewTunnelInputToTarget(
    networkId: string,
    targetNodeId: string,
    targetPort: string,
  ): Promise<SerializedNetwork> {
    return api
      .post(`/networks/${networkId}/tunnel-input-connections`, { targetNodeId, targetPort })
      .then((r) => r.data);
  },

  /** Create a tunnel output port from an existing source port and connect it. */
  connectToNewTunnelOutput(
    networkId: string,
    sourceNodeId: string,
    sourcePort: string,
  ): Promise<SerializedNetwork> {
    return api
      .post(`/networks/${networkId}/tunnel-output-connections`, { sourceNodeId, sourcePort })
      .then((r) => r.data);
  },

  /** Remove a tunnel port from a subnetwork */
  removeTunnelPort(
    networkId: string,
    portName: string,
    direction: 'input' | 'output',
  ): Promise<void> {
    return api
      .delete(`/networks/${networkId}/tunnel-ports/${portName}`, {
        params: { direction },
      })
      .then(() => undefined);
  },

  /** Rename a tunnel port on a subnetwork. */
  renameTunnelPort(
    networkId: string,
    oldName: string,
    newName: string,
    direction: 'input' | 'output',
  ): Promise<void> {
    return api
      .put(`/networks/${networkId}/tunnel-ports/${oldName}`, {
        newName,
        direction,
      })
      .then(() => undefined);
  },

  /** Get registered node type names */
  getNodeTypes(): Promise<string[]> {
    return api.get('/node-types').then((r) => r.data);
  },

  /** Get available node port value types. */
  getPortTypes(): Promise<string[]> {
    return api.get('/port-types').then((r) => r.data);
  },

  /** Unblock the server executor when in step mode. */
  stepResume(): Promise<void> {
    return api.post('/step/resume').then(() => undefined);
  },

  /** Trigger execution from a specific node. Pass step=true to enable step-by-step tracing. */
  execute(networkId: string, nodeId: string, step = false): Promise<void> {
    const url = `/networks/${networkId}/execute/${nodeId}${step ? '?step=true' : ''}`;
    return api.post(url).then(() => undefined);
  },

  /** Submit a human response to an awaiting HumanInputNode. */
  submitHumanInput(runId: string, networkId: string, nodeId: string, response: string): Promise<void> {
    return api
      .post(`/executions/${runId}/nodes/${nodeId}/human-input`, { response })
      .then(() => undefined);
  },
};
