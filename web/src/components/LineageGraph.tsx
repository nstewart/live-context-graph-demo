import { useCallback, useMemo } from 'react';
import {
  ReactFlow,
  Node,
  Edge,
  Background,
  Position,
  NodeMouseHandler,
} from '@xyflow/react';
import dagre from 'dagre';
import '@xyflow/react/dist/style.css';

// Node type colors
const nodeColors = {
  source: { bg: '#3b82f6', border: '#1d4ed8', text: '#ffffff' }, // Blue
  view: { bg: '#6b7280', border: '#374151', text: '#ffffff' }, // Gray
  mv: { bg: '#10b981', border: '#059669', text: '#ffffff' }, // Green
  index: { bg: '#8b5cf6', border: '#6d28d9', text: '#ffffff' }, // Purple
};

// Custom node styles
const getNodeStyle = (type: keyof typeof nodeColors, isSelected: boolean = false) => ({
  background: nodeColors[type].bg,
  border: `2px solid ${isSelected ? '#fbbf24' : nodeColors[type].border}`,
  borderRadius: '8px',
  padding: '10px 16px',
  color: nodeColors[type].text,
  fontSize: '12px',
  fontWeight: 500,
  minWidth: '120px',
  textAlign: 'center' as const,
  cursor: 'pointer',
  boxShadow: isSelected ? '0 0 12px rgba(251, 191, 36, 0.6)' : undefined,
});

// Node definitions (without positions - dagre will compute them)
// Based on actual Materialize dependencies from mz_internal.mz_object_dependencies
const nodeDefinitions = [
  { id: 'triples', label: 'triples', type: 'source' as const },
  { id: 'customers_flat', label: 'customers_flat', type: 'view' as const },
  { id: 'stores_flat', label: 'stores_flat', type: 'view' as const },
  { id: 'products_flat', label: 'products_flat', type: 'view' as const },
  { id: 'order_lines_base', label: 'order_lines_base', type: 'view' as const },
  { id: 'delivery_tasks_flat', label: 'delivery_tasks_flat', type: 'view' as const },
  { id: 'orders_flat_mv', label: 'orders_flat_mv', type: 'mv' as const },
  { id: 'order_lines_flat_mv', label: 'order_lines_flat_mv', type: 'mv' as const },
  { id: 'store_inventory_mv', label: 'store_inventory_mv', type: 'mv' as const },
  { id: 'orders_with_lines_mv', label: 'orders_with_lines_mv', type: 'mv' as const, highlighted: true },
  { id: 'inventory_items_with_dynamic_pricing', label: 'dynamic_pricing', type: 'view' as const },
  { id: 'inventory_items_with_dynamic_pricing_mv', label: 'dynamic_pricing_mv', type: 'mv' as const, highlighted: true },
];

// Edge definitions based on actual Materialize dependencies
const edgeDefinitions = [
  // Tier 0 → Tier 1: triples to base views
  { source: 'triples', target: 'customers_flat' },
  { source: 'triples', target: 'stores_flat' },
  { source: 'triples', target: 'products_flat' },
  { source: 'triples', target: 'order_lines_base' },
  { source: 'triples', target: 'delivery_tasks_flat' },
  // Tier 0 → Tier 2: triples directly to orders_flat_mv
  { source: 'triples', target: 'orders_flat_mv' },
  // Tier 1 → Tier 2: base views to order_lines_flat_mv
  { source: 'order_lines_base', target: 'order_lines_flat_mv' },
  { source: 'products_flat', target: 'order_lines_flat_mv' },
  // Tier 1,2 → Tier 3: to store_inventory_mv
  { source: 'triples', target: 'store_inventory_mv' },
  { source: 'products_flat', target: 'store_inventory_mv' },
  { source: 'stores_flat', target: 'store_inventory_mv' },
  { source: 'orders_flat_mv', target: 'store_inventory_mv' },
  { source: 'order_lines_flat_mv', target: 'store_inventory_mv' },
  // Tier 1,2 → Tier 4: to orders_with_lines_mv
  { source: 'customers_flat', target: 'orders_with_lines_mv' },
  { source: 'stores_flat', target: 'orders_with_lines_mv' },
  { source: 'delivery_tasks_flat', target: 'orders_with_lines_mv' },
  { source: 'orders_flat_mv', target: 'orders_with_lines_mv' },
  { source: 'order_lines_flat_mv', target: 'orders_with_lines_mv' },
  // Tier 2,3 → Tier 4: to dynamic_pricing
  { source: 'store_inventory_mv', target: 'inventory_items_with_dynamic_pricing' },
  { source: 'orders_flat_mv', target: 'inventory_items_with_dynamic_pricing' },
  { source: 'order_lines_flat_mv', target: 'inventory_items_with_dynamic_pricing' },
  // Tier 4 → Tier 5: dynamic_pricing to dynamic_pricing_mv
  { source: 'inventory_items_with_dynamic_pricing', target: 'inventory_items_with_dynamic_pricing_mv' },
];

// Edge style
const edgeStyle = {
  stroke: '#94a3b8',
  strokeWidth: 2,
};

// Node dimensions for dagre layout
const NODE_WIDTH = 150;
const NODE_HEIGHT = 40;

// Use dagre to compute node positions
function getLayoutedElements(
  nodeDefs: typeof nodeDefinitions,
  edgeDefs: typeof edgeDefinitions,
  selectedNodeId: string | null | undefined
): { nodes: Node[]; edges: Edge[] } {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  // Configure dagre for left-to-right layout with good spacing
  dagreGraph.setGraph({
    rankdir: 'LR',      // Left to right
    nodesep: 50,        // Vertical separation between nodes
    ranksep: 100,       // Horizontal separation between ranks
    marginx: 20,
    marginy: 20,
  });

  // Add nodes to dagre
  nodeDefs.forEach((node) => {
    dagreGraph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  });

  // Add edges to dagre
  edgeDefs.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  // Run the layout algorithm
  dagre.layout(dagreGraph);

  // Create React Flow nodes with computed positions
  const nodes: Node[] = nodeDefs.map((nodeDef) => {
    const nodeWithPosition = dagreGraph.node(nodeDef.id);
    const isSelected = nodeDef.id === selectedNodeId;
    const isHighlighted = nodeDef.highlighted || false;

    let style = getNodeStyle(nodeDef.type, isSelected);
    if (isHighlighted && !isSelected) {
      style = {
        ...style,
        border: '3px solid #059669',
        boxShadow: '0 0 10px rgba(16, 185, 129, 0.4)',
      };
    }

    return {
      id: nodeDef.id,
      position: {
        // Dagre gives center position, React Flow uses top-left
        x: nodeWithPosition.x - NODE_WIDTH / 2,
        y: nodeWithPosition.y - NODE_HEIGHT / 2,
      },
      data: { label: nodeDef.label },
      style,
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    };
  });

  // Create React Flow edges
  const edges: Edge[] = edgeDefs.map((edgeDef, index) => ({
    id: `e-${edgeDef.source}-${edgeDef.target}-${index}`,
    source: edgeDef.source,
    target: edgeDef.target,
    style: edgeStyle,
    animated: true,
  }));

  return { nodes, edges };
}

interface LineageGraphProps {
  selectedNodeId?: string | null;
  onNodeClick?: (nodeId: string) => void;
}

export function LineageGraph({ selectedNodeId, onNodeClick }: LineageGraphProps) {
  // Compute layout with dagre - memoized to avoid recalculating on every render
  const { nodes, edges } = useMemo(
    () => getLayoutedElements(nodeDefinitions, edgeDefinitions, selectedNodeId),
    [selectedNodeId]
  );

  const handleNodeClick: NodeMouseHandler = useCallback(
    (_, node) => {
      if (onNodeClick) {
        onNodeClick(node.id);
      }
    },
    [onNodeClick]
  );

  return (
    <div className="w-full">
      {/* Legend */}
      <div className="flex gap-6 mb-4 text-sm">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded" style={{ background: nodeColors.source.bg }} />
          <span className="text-gray-600">Source (CDC)</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded" style={{ background: nodeColors.view.bg }} />
          <span className="text-gray-600">View</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded" style={{ background: nodeColors.mv.bg }} />
          <span className="text-gray-600">Materialized View</span>
        </div>
        {selectedNodeId && (
          <div className="flex items-center gap-2 ml-auto">
            <div className="w-4 h-4 rounded border-2 border-yellow-400" style={{ background: 'transparent' }} />
            <span className="text-gray-600">Selected</span>
          </div>
        )}
      </div>

      {/* Graph */}
      <div className="h-[350px] w-full border border-gray-200 rounded-lg bg-gray-50">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodeClick={handleNodeClick}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={true}
          panOnDrag={false}
          zoomOnScroll={false}
          zoomOnPinch={false}
          zoomOnDoubleClick={false}
          preventScrolling={false}
        >
          <Background color="#e5e7eb" gap={16} />
        </ReactFlow>
      </div>

      {/* Description */}
      <p className="mt-3 text-sm text-gray-500">
        Two data products from the same <span className="font-medium text-blue-600">triples</span> source:{' '}
        <span className="font-medium text-green-600">orders_with_lines_mv</span> (order details) and{' '}
        <span className="font-medium text-green-600">dynamic_pricing_mv</span> (live pricing with 9 factors).
        The API joins them at query time for a consistent snapshot. Click any node to view its SQL.
      </p>
    </div>
  );
}

export default LineageGraph;
