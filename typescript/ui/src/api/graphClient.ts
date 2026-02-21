import axios from 'axios';
import type {
  SerializedNetwork,
  NetworkListItem,
} from '../types/uiTypes';

const BASE = '/api';
const api = axios.create({ baseURL: BASE });

export const graphClient = {
  /** Get the root network id */
  getRootNetwork(): Promise<{ id: string; name: string }> {
    return api.get('/networks/root').then((r) => r.data);
  },

  /** List all networks */
  listNetworks(): Promise<NetworkListItem[]> {
    return api.get('/networks').then((r) => r.data);
  },

  /** Fetch a network's full graph */
  getNetwork(id: string): Promise<SerializedNetwork> {
    return api.get(`/networks/${id}`).then((r) => r.data);
  },

  /** Create a subnetwork inside `parentId` */
  createSubnetwork(parentId: string, name: string): Promise<{ id: string; name: string }> {
    return api.post(`/networks/${parentId}/networks`, { name }).then((r) => r.data);
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

  /** Add a tunnel input or output port to a subnetwork */
  addTunnelPort(
    networkId: string,
    name: string,
    direction: 'input' | 'output',
  ): Promise<SerializedNetwork> {
    return api
      .post(`/networks/${networkId}/tunnel-ports`, { name, direction })
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

  /** Get registered node type names */
  getNodeTypes(): Promise<string[]> {
    return api.get('/node-types').then((r) => r.data);
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
};
