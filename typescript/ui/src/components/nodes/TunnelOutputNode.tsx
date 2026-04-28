import React from 'react';
import { Node, NodeProps } from '@xyflow/react';
import type { NodeData } from '../../types/uiTypes';
import { TunnelNodeCard } from './TunnelNodeCard';

function TunnelOutputNodeComponent({ id, data, selected }: NodeProps<Node<NodeData>>) {
  return <TunnelNodeCard id={id} data={data} selected={selected ?? false} mode="output" />;
}

export const TunnelOutputNode = React.memo(
  TunnelOutputNodeComponent,
  (prev, next) =>
    prev.id === next.id &&
    prev.selected === next.selected &&
    prev.data === next.data &&
    prev.dragging === next.dragging,
);
TunnelOutputNode.displayName = 'TunnelOutputNode';
