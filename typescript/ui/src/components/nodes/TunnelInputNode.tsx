import React from 'react';
import { Node, NodeProps } from '@xyflow/react';
import type { NodeData } from '../../types/uiTypes';
import { TunnelNodeCard } from './TunnelNodeCard';

function TunnelInputNodeComponent({ id, data, selected }: NodeProps<Node<NodeData>>) {
  return <TunnelNodeCard id={id} data={data} selected={selected ?? false} mode="input" />;
}

export const TunnelInputNode = React.memo(
  TunnelInputNodeComponent,
  (prev, next) =>
    prev.id === next.id &&
    prev.selected === next.selected &&
    prev.data === next.data &&
    prev.dragging === next.dragging,
);
TunnelInputNode.displayName = 'TunnelInputNode';
