import {
  ReactFlow,
  Node,
  Edge,
  Background,
  useNodesState,
  useEdgesState,
  Position,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

// Node type colors
const nodeColors = {
  source: { bg: '#3b82f6', border: '#1d4ed8', text: '#ffffff' }, // Blue
  view: { bg: '#6b7280', border: '#374151', text: '#ffffff' }, // Gray
  mv: { bg: '#10b981', border: '#059669', text: '#ffffff' }, // Green
  index: { bg: '#8b5cf6', border: '#6d28d9', text: '#ffffff' }, // Purple
};

// Custom node styles
const getNodeStyle = (type: keyof typeof nodeColors) => ({
  background: nodeColors[type].bg,
  border: `2px solid ${nodeColors[type].border}`,
  borderRadius: '8px',
  padding: '10px 16px',
  color: nodeColors[type].text,
  fontSize: '12px',
  fontWeight: 500,
  minWidth: '120px',
  textAlign: 'center' as const,
});

// Define the lineage nodes for orders_with_lines_mv
const initialNodes: Node[] = [
  // Tier 0: Source
  {
    id: 'triples',
    position: { x: 0, y: 150 },
    data: { label: 'triples' },
    style: getNodeStyle('source'),
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  },

  // Tier 1: Entity Views (flat views derived from triples)
  {
    id: 'customers_flat',
    position: { x: 200, y: 0 },
    data: { label: 'customers_flat' },
    style: getNodeStyle('view'),
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  },
  {
    id: 'stores_flat',
    position: { x: 200, y: 70 },
    data: { label: 'stores_flat' },
    style: getNodeStyle('view'),
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  },
  {
    id: 'products_flat',
    position: { x: 200, y: 140 },
    data: { label: 'products_flat' },
    style: getNodeStyle('view'),
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  },
  {
    id: 'order_lines_base',
    position: { x: 200, y: 210 },
    data: { label: 'order_lines_base' },
    style: getNodeStyle('view'),
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  },
  {
    id: 'delivery_tasks_flat',
    position: { x: 200, y: 280 },
    data: { label: 'delivery_tasks_flat' },
    style: getNodeStyle('view'),
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  },

  // Tier 2: Materialized Views
  {
    id: 'orders_flat_mv',
    position: { x: 420, y: 80 },
    data: { label: 'orders_flat_mv' },
    style: getNodeStyle('mv'),
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  },
  {
    id: 'order_lines_flat_mv',
    position: { x: 420, y: 180 },
    data: { label: 'order_lines_flat_mv' },
    style: getNodeStyle('mv'),
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  },

  // Tier 3: Final Data Product
  {
    id: 'orders_with_lines_mv',
    position: { x: 640, y: 130 },
    data: { label: 'orders_with_lines_mv' },
    style: {
      ...getNodeStyle('mv'),
      border: '3px solid #059669',
      boxShadow: '0 0 10px rgba(16, 185, 129, 0.4)',
    },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  },
];

// Define edges with animated flow
const edgeStyle = {
  stroke: '#94a3b8',
  strokeWidth: 2,
};

const initialEdges: Edge[] = [
  // Triples to flat views
  { id: 'e-triples-customers', source: 'triples', target: 'customers_flat', style: edgeStyle, animated: true },
  { id: 'e-triples-stores', source: 'triples', target: 'stores_flat', style: edgeStyle, animated: true },
  { id: 'e-triples-products', source: 'triples', target: 'products_flat', style: edgeStyle, animated: true },
  { id: 'e-triples-orderlines', source: 'triples', target: 'order_lines_base', style: edgeStyle, animated: true },
  { id: 'e-triples-tasks', source: 'triples', target: 'delivery_tasks_flat', style: edgeStyle, animated: true },

  // Triples directly to orders_flat_mv (uses CTE on triples)
  { id: 'e-triples-orders', source: 'triples', target: 'orders_flat_mv', style: edgeStyle, animated: true },

  // Flat views to order_lines_flat_mv
  { id: 'e-orderlines-mv', source: 'order_lines_base', target: 'order_lines_flat_mv', style: edgeStyle, animated: true },
  { id: 'e-products-mv', source: 'products_flat', target: 'order_lines_flat_mv', style: edgeStyle, animated: true },

  // All to final orders_with_lines_mv
  { id: 'e-customers-final', source: 'customers_flat', target: 'orders_with_lines_mv', style: edgeStyle, animated: true },
  { id: 'e-stores-final', source: 'stores_flat', target: 'orders_with_lines_mv', style: edgeStyle, animated: true },
  { id: 'e-tasks-final', source: 'delivery_tasks_flat', target: 'orders_with_lines_mv', style: edgeStyle, animated: true },
  { id: 'e-ordersflat-final', source: 'orders_flat_mv', target: 'orders_with_lines_mv', style: edgeStyle, animated: true },
  { id: 'e-orderlinesflat-final', source: 'order_lines_flat_mv', target: 'orders_with_lines_mv', style: edgeStyle, animated: true },

];

export function LineageGraph() {
  const [nodes] = useNodesState(initialNodes);
  const [edges] = useEdgesState(initialEdges);

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
      </div>

      {/* Graph */}
      <div className="h-[350px] w-full border border-gray-200 rounded-lg bg-gray-50">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
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
        Data flows from the <span className="font-medium text-blue-600">triples</span> source table through
        intermediate views to the <span className="font-medium text-green-600">orders_with_lines_mv</span> materialized
        view, which powers the Orders page. Changes propagate incrementally in real-time.
      </p>
    </div>
  );
}

export default LineageGraph;
