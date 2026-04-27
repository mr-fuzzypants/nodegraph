import { Node, NodeProps } from '@xyflow/react';
import type { NodeData } from '../../types/uiTypes';
import { TunnelNodeCard } from './TunnelNodeCard';

export function TunnelInputNode({ id, data, selected }: NodeProps<Node<NodeData>>) {
  return <TunnelNodeCard id={id} data={data} selected={selected} mode="input" />;
}
