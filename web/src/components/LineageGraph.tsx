import { useCallback, useMemo } from 'react';
import {
  ReactFlow,
  Node,
  Edge,
  Background,
  Position,
  Handle,
  MarkerType,
  NodeMouseHandler,
  NodeTypes,
} from '@xyflow/react';
import dagre from 'dagre';
import '@xyflow/react/dist/style.css';

type MedallionLayer = 'source_systems' | 'sources' | 'bronze' | 'silver' | 'gold';

// Node type colors (object type)
const nodeColors = {
  source: { bg: '#3b82f6', border: '#1d4ed8', text: '#ffffff' },
  view: { bg: '#6b7280', border: '#374151', text: '#ffffff' },
  mv: { bg: '#10b981', border: '#059669', text: '#ffffff' },
  index: { bg: '#8b5cf6', border: '#6d28d9', text: '#ffffff' },
  tables: { bg: '#0891b2', border: '#0e7490', text: '#ffffff' },
};

// Medallion layer colors
const medallionColors: Record<MedallionLayer, {
  bg: string;
  border: string;
  labelColor: string;
  legendLabel: string;
}> = {
  source_systems: {
    bg: 'rgba(148, 163, 184, 0.07)',
    border: 'rgba(148, 163, 184, 0.30)',
    labelColor: '#475569',
    legendLabel: 'Source Systems',
  },
  sources: {
    bg: 'rgba(59, 130, 246, 0.07)',
    border: 'rgba(59, 130, 246, 0.28)',
    labelColor: '#1d4ed8',
    legendLabel: 'Sources',
  },
  bronze: {
    bg: 'rgba(180, 83, 9, 0.07)',
    border: 'rgba(180, 83, 9, 0.28)',
    labelColor: '#92400e',
    legendLabel: 'Bronze',
  },
  silver: {
    bg: 'rgba(100, 116, 139, 0.07)',
    border: 'rgba(100, 116, 139, 0.28)',
    labelColor: '#475569',
    legendLabel: 'Silver',
  },
  gold: {
    bg: 'rgba(234, 179, 8, 0.09)',
    border: 'rgba(234, 179, 8, 0.5)',
    labelColor: '#854d0e',
    legendLabel: 'Gold',
  },
};

// Swim-lane label band
const BandNode = ({ data }: { data: { layer: MedallionLayer } }) => {
  const colors = medallionColors[data.layer];
  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'center',
        paddingTop: '6px',
        userSelect: 'none',
      }}
    >
      <span
        style={{
          fontSize: '12px',
          fontWeight: 700,
          letterSpacing: '0.1em',
          textTransform: 'uppercase',
          color: colors.labelColor,
          opacity: 0.75,
        }}
      >
        {colors.legendLabel}
      </span>
    </div>
  );
};

// Fine-grained access control wrapper (behind bronze/silver/gold bands)
const FgacBandNode = () => (
  <div
    style={{
      width: '100%',
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'space-between',
      padding: '10px',
      boxSizing: 'border-box',
      userSelect: 'none',
      pointerEvents: 'none',
    }}
  >
    {/* Header rectangle at top */}
    <div
      style={{
        background: 'rgba(124, 58, 237, 0.12)',
        border: '1px solid rgba(124, 58, 237, 0.45)',
        borderRadius: '6px',
        padding: '6px 14px',
        textAlign: 'center',
        flexShrink: 0,
      }}
    >
      <span style={{ fontSize: '13px', fontWeight: 700, color: '#7c3aed' }}>
        Incremental View Maintenance via Timely Dataflow
      </span>
    </div>
    {/* Materialize branding at bottom */}
    <div style={{ textAlign: 'center', paddingBottom: '2px' }}>
      <span
        style={{
          fontSize: '13px',
          fontWeight: 700,
          color: '#7c3aed',
          opacity: 0.5,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
        }}
      >
        Materialize
      </span>
    </div>
    <Handle
      type="target"
      position={Position.Top}
      id="top"
      style={{ pointerEvents: 'all', opacity: 0 }}
    />
  </div>
);

// OLAP wrapper band — Batch scenario: covers Sources + Bronze + Silver + Gold
const OlapBandNode = () => (
  <div
    style={{
      width: '100%',
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'space-between',
      padding: '10px',
      boxSizing: 'border-box',
      userSelect: 'none',
      pointerEvents: 'none',
    }}
  >
    {/* Header rectangle at top */}
    <div
      style={{
        background: 'rgba(217, 119, 6, 0.12)',
        border: '1px solid rgba(217, 119, 6, 0.45)',
        borderRadius: '6px',
        padding: '6px 14px',
        textAlign: 'center',
        flexShrink: 0,
      }}
    >
      <span style={{ fontSize: '13px', fontWeight: 700, color: '#92400e' }}>
        Scheduled Refresh
      </span>
    </div>
    {/* OLAP branding at bottom */}
    <div style={{ textAlign: 'center', paddingBottom: '2px' }}>
      <span
        style={{
          fontSize: '13px',
          fontWeight: 700,
          color: '#d97706',
          opacity: 0.5,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
        }}
      >
        OLAP
      </span>
    </div>
    <Handle
      type="target"
      position={Position.Top}
      id="top"
      style={{ pointerEvents: 'all', opacity: 0 }}
    />
  </div>
);

// Source wrapper band — Postgres scenario: covers Bronze + Silver + Gold
const SourceWrapperBandNode = () => (
  <div
    style={{
      width: '100%',
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'space-between',
      padding: '10px',
      boxSizing: 'border-box',
      userSelect: 'none',
      pointerEvents: 'none',
    }}
  >
    {/* Header rectangle at top */}
    <div
      style={{
        background: 'rgba(30, 64, 175, 0.10)',
        border: '1px solid rgba(30, 64, 175, 0.40)',
        borderRadius: '6px',
        padding: '6px 14px',
        textAlign: 'center',
        flexShrink: 0,
      }}
    >
      <span style={{ fontSize: '13px', fontWeight: 700, color: '#1e40af' }}>
        Reactive query processing
      </span>
    </div>
    {/* PostgreSQL branding at bottom */}
    <div style={{ textAlign: 'center', paddingBottom: '2px' }}>
      <span
        style={{
          fontSize: '13px',
          fontWeight: 700,
          color: '#1e40af',
          opacity: 0.5,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
        }}
      >
        OLTP
      </span>
    </div>
    <Handle
      type="target"
      position={Position.Top}
      id="top"
      style={{ pointerEvents: 'all', opacity: 0 }}
    />
  </div>
);

// Source Systems column node (CRM / ERP / Apps / External Data)
const SourceSystemsNode = () => (
  <div
    style={{
      width: '100%',
      height: '100%',
      background: '#f8fafc',
      border: '1.5px solid #94a3b8',
      borderRadius: '10px',
      padding: '8px 10px',
      display: 'flex',
      flexDirection: 'column',
      gap: '5px',
      boxSizing: 'border-box',
      userSelect: 'none',
    }}
  >
    <Handle type="target" position={Position.Top} id="top" style={{ opacity: 0 }} />
    <div
      style={{
        fontSize: '12px',
        fontWeight: 700,
        color: '#374151',
        textAlign: 'center',
        borderBottom: '1px solid #e5e7eb',
        paddingBottom: '4px',
        marginBottom: '2px',
      }}
    >
      Source Systems
    </div>
    {['CRM', 'ERP', 'Apps', 'External Data'].map((s) => (
      <div
        key={s}
        style={{
          fontSize: '11px',
          color: '#475569',
          background: '#f1f5f9',
          border: '1px solid #e2e8f0',
          borderRadius: '4px',
          padding: '3px 6px',
          textAlign: 'center',
        }}
      >
        {s}
      </div>
    ))}
    <Handle type="source" position={Position.Right} id="right" style={{ opacity: 0 }} />
  </div>
);

// Agent node
const AgentNode = () => (
  <div
    style={{
      width: '100%',
      height: '100%',
      background: '#fff7ed',
      border: '2px solid #f97316',
      borderRadius: '10px',
      padding: '8px 12px',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: '3px',
      boxSizing: 'border-box',
      userSelect: 'none',
    }}
  >
    <span style={{ fontSize: '22px', lineHeight: 1 }}>🤖</span>
    <span style={{ fontSize: '13px', fontWeight: 700, color: '#9a3412' }}>Agent</span>
    <Handle type="source" position={Position.Right} id="right" style={{ opacity: 0 }} />
    <Handle type="source" position={Position.Bottom} id="bottom" style={{ opacity: 0 }} />
  </div>
);

// MCP Server node
const McpNode = () => (
  <div
    style={{
      width: '100%',
      height: '100%',
      background: '#fdf4ff',
      border: '2px solid #a855f7',
      borderRadius: '10px',
      padding: '8px 12px',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: '2px',
      boxSizing: 'border-box',
      userSelect: 'none',
    }}
  >
    <span style={{ fontSize: '20px', lineHeight: 1 }}>⚙️</span>
    <span style={{ fontSize: '13px', fontWeight: 700, color: '#7e22ce' }}>MCP Server</span>
    <Handle type="target" position={Position.Left} id="left" style={{ opacity: 0 }} />
    <Handle type="source" position={Position.Bottom} id="bottom" style={{ opacity: 0 }} />
  </div>
);

const nodeTypes: NodeTypes = {
  band: BandNode,
  fgac_band: FgacBandNode,
  olap_band: OlapBandNode,
  source_wrapper_band: SourceWrapperBandNode,
  source_systems_node: SourceSystemsNode,
  agent_node: AgentNode,
  mcp_node: McpNode,
};

// Custom node styles for lineage nodes
const getNodeStyle = (type: keyof typeof nodeColors, isSelected: boolean = false) => ({
  background: nodeColors[type].bg,
  border: `2px solid ${isSelected ? '#fbbf24' : nodeColors[type].border}`,
  borderRadius: '8px',
  padding: '10px 16px',
  color: nodeColors[type].text,
  fontSize: '13px',
  fontWeight: 500,
  minWidth: '120px',
  textAlign: 'center' as const,
  cursor: 'pointer',
  boxShadow: isSelected ? '0 0 12px rgba(251, 191, 36, 0.6)' : undefined,
});

// Lineage node definitions (positions computed by dagre)
const nodeDefinitions: Array<{
  id: string;
  label: string;
  type: keyof typeof nodeColors;
  medallionLayer: MedallionLayer;
  highlighted?: boolean;
}> = [
  { id: 'triples', label: 'OLTP', type: 'source', medallionLayer: 'sources' },
  { id: 'customers_flat', label: 'customers_flat', type: 'view', medallionLayer: 'bronze' },
  { id: 'stores_flat', label: 'stores_flat', type: 'view', medallionLayer: 'bronze' },
  { id: 'products_flat', label: 'products_flat', type: 'view', medallionLayer: 'bronze' },
  { id: 'order_lines_base', label: 'order_lines_base', type: 'view', medallionLayer: 'bronze' },
  { id: 'delivery_tasks_flat', label: 'delivery_tasks_flat', type: 'view', medallionLayer: 'bronze' },
  { id: 'orders_flat_mv', label: 'orders_flat_mv', type: 'mv', medallionLayer: 'bronze' },
  { id: 'order_lines_flat_mv', label: 'order_lines_flat_mv', type: 'mv', medallionLayer: 'bronze' },
  { id: 'store_inventory_mv', label: 'store_inventory_mv', type: 'mv', medallionLayer: 'silver' },
  { id: 'orders_with_lines_mv', label: 'orders_with_lines_mv', type: 'mv', highlighted: true, medallionLayer: 'silver' },
  { id: 'inventory_items_with_dynamic_pricing', label: 'dynamic_pricing', type: 'view', medallionLayer: 'gold' },
  { id: 'inventory_items_with_dynamic_pricing_mv', label: 'dynamic_pricing_mv', type: 'mv', highlighted: true, medallionLayer: 'gold' },
];

// Lineage edge definitions
const edgeDefinitions = [
  { source: 'triples', target: 'customers_flat' },
  { source: 'triples', target: 'stores_flat' },
  { source: 'triples', target: 'products_flat' },
  { source: 'triples', target: 'order_lines_base' },
  { source: 'triples', target: 'delivery_tasks_flat' },
  { source: 'triples', target: 'orders_flat_mv' },
  { source: 'order_lines_base', target: 'order_lines_flat_mv' },
  { source: 'products_flat', target: 'order_lines_flat_mv' },
  { source: 'triples', target: 'store_inventory_mv' },
  { source: 'products_flat', target: 'store_inventory_mv' },
  { source: 'stores_flat', target: 'store_inventory_mv' },
  { source: 'orders_flat_mv', target: 'store_inventory_mv' },
  { source: 'order_lines_flat_mv', target: 'store_inventory_mv' },
  { source: 'customers_flat', target: 'orders_with_lines_mv' },
  { source: 'stores_flat', target: 'orders_with_lines_mv' },
  { source: 'delivery_tasks_flat', target: 'orders_with_lines_mv' },
  { source: 'orders_flat_mv', target: 'orders_with_lines_mv' },
  { source: 'order_lines_flat_mv', target: 'orders_with_lines_mv' },
  { source: 'store_inventory_mv', target: 'inventory_items_with_dynamic_pricing' },
  { source: 'orders_flat_mv', target: 'inventory_items_with_dynamic_pricing' },
  { source: 'order_lines_flat_mv', target: 'inventory_items_with_dynamic_pricing' },
  { source: 'inventory_items_with_dynamic_pricing', target: 'inventory_items_with_dynamic_pricing_mv' },
];

const edgeStyle = { stroke: '#94a3b8', strokeWidth: 2 };

// Node dimensions for dagre layout
const NODE_WIDTH = 168;
const NODE_HEIGHT = 44;
const BAND_PADDING_X = 20;
const BAND_PADDING_Y = 32;
// Source Systems box (taller to accommodate 4 items)
const SS_W = 150;
const SS_H = 170;
// Floating nodes above the graph
const AGENT_W = 100;
const AGENT_H = 76;
const MCP_W = 118;
const MCP_H = 76;
// FGAC wrapper extra space: top accommodates the header rectangle, bottom accommodates "Materialize"
const FGAC_LABEL_TOP = 54;
const FGAC_LABEL_BOTTOM = 32;
const FGAC_PAD = 10;
const FLOAT_GAP = 28;

function getLayoutedElements(
  nodeDefs: typeof nodeDefinitions,
  edgeDefs: typeof edgeDefinitions,
  selectedNodeId: string | null | undefined,
  scenario: 'materialize' | 'postgres' | 'batch' = 'materialize'
): { nodes: Node[]; edges: Edge[] } {
  const isMaterialize = scenario === 'materialize';
  const isPostgres = scenario === 'postgres';
  const isBatch = scenario === 'batch';

  // In Postgres mode, triples lives in the Bronze column (no separate CDC source lane)
  const effectiveNodeDefs = nodeDefs.map((n) =>
    n.id === 'triples' && isPostgres
      ? { ...n, label: 'triples', medallionLayer: 'bronze' as MedallionLayer }
      : n
  );

  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({ rankdir: 'LR', nodesep: 50, ranksep: 100, marginx: 20, marginy: 20 });

  // Add lineage nodes + source_systems_box to dagre for layout
  effectiveNodeDefs.forEach((node) => {
    dagreGraph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  });
  edgeDefs.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });
  dagreGraph.setNode('source_systems_box', { width: SS_W, height: SS_H });
  dagreGraph.setEdge('source_systems_box', 'triples');

  dagre.layout(dagreGraph);

  // Compute bounding boxes per medallion layer and overall graph
  const layerBounds: Record<MedallionLayer, { minX: number; maxX: number }> = {
    source_systems: { minX: Infinity, maxX: -Infinity },
    sources: { minX: Infinity, maxX: -Infinity },
    bronze: { minX: Infinity, maxX: -Infinity },
    silver: { minX: Infinity, maxX: -Infinity },
    gold: { minX: Infinity, maxX: -Infinity },
  };
  let graphMinY = Infinity;
  let graphMaxY = -Infinity;

  effectiveNodeDefs.forEach((nodeDef) => {
    const pos = dagreGraph.node(nodeDef.id);
    graphMinY = Math.min(graphMinY, pos.y - NODE_HEIGHT / 2);
    graphMaxY = Math.max(graphMaxY, pos.y + NODE_HEIGHT / 2);
    const b = layerBounds[nodeDef.medallionLayer];
    b.minX = Math.min(b.minX, pos.x - NODE_WIDTH / 2);
    b.maxX = Math.max(b.maxX, pos.x + NODE_WIDTH / 2);
  });

  // Include source_systems_box in graph + layer bounds
  const ssPos = dagreGraph.node('source_systems_box');
  graphMinY = Math.min(graphMinY, ssPos.y - SS_H / 2);
  graphMaxY = Math.max(graphMaxY, ssPos.y + SS_H / 2);
  layerBounds.source_systems.minX = ssPos.x - SS_W / 2;
  layerBounds.source_systems.maxX = ssPos.x + SS_W / 2;

  // Swim-lane band nodes for each layer
  const bandNodes: Node[] = (Object.keys(layerBounds) as MedallionLayer[])
    .filter((layer) => layerBounds[layer].minX !== Infinity)
    .map((layer) => {
      const b = layerBounds[layer];
      const colors = medallionColors[layer];
      return {
        id: `__band__${layer}`,
        type: 'band',
        position: { x: b.minX - BAND_PADDING_X, y: graphMinY - BAND_PADDING_Y },
        style: {
          width: b.maxX - b.minX + BAND_PADDING_X * 2,
          height: graphMaxY - graphMinY + BAND_PADDING_Y * 2,
          background: colors.bg,
          border: `1.5px solid ${colors.border}`,
          borderRadius: '10px',
          pointerEvents: 'none' as const,
        },
        data: { label: '', layer },
        zIndex: -1,
        selectable: false,
        draggable: false,
        focusable: false,
      };
    });

  // Outer wrapper band — spans bronze → gold in both scenarios.
  // In Postgres mode, triples has been moved into bronze so sources is empty.
  // In Materialize mode, sources stays separate (left of the wrapper).
  const wrapperMinX = Math.min(layerBounds.bronze.minX, layerBounds.silver.minX, layerBounds.gold.minX);
  const wrapperMaxX = Math.max(layerBounds.bronze.maxX, layerBounds.silver.maxX, layerBounds.gold.maxX);
  const wrapperLeft = wrapperMinX - BAND_PADDING_X - FGAC_PAD;
  // All scenarios have a header rectangle, so all need the same top clearance
  const wrapperLabelTop = FGAC_LABEL_TOP;
  const wrapperTop = graphMinY - BAND_PADDING_Y - wrapperLabelTop - FGAC_PAD;
  const wrapperWidth = wrapperMaxX - wrapperMinX + (BAND_PADDING_X + FGAC_PAD) * 2;
  const wrapperHeight = graphMaxY - graphMinY + (BAND_PADDING_Y + FGAC_PAD) * 2 + wrapperLabelTop + FGAC_LABEL_BOTTOM;

  const outerBandNode: Node = {
    id: isMaterialize ? '__fgac__' : isBatch ? '__olap__' : '__source_wrapper__',
    type: isMaterialize ? 'fgac_band' : isBatch ? 'olap_band' : 'source_wrapper_band',
    position: { x: wrapperLeft, y: wrapperTop },
    style: {
      width: wrapperWidth,
      height: wrapperHeight,
      background: isMaterialize
        ? 'rgba(124, 58, 237, 0.04)'
        : isBatch
          ? 'rgba(217, 119, 6, 0.04)'
          : 'rgba(30, 64, 175, 0.04)',
      border: isMaterialize
        ? '1.5px solid rgba(124, 58, 237, 0.35)'
        : isBatch
          ? '1.5px solid rgba(217, 119, 6, 0.30)'
          : '1.5px solid rgba(30, 64, 175, 0.30)',
      borderRadius: '12px',
    },
    data: { label: '' },
    zIndex: -2,
    selectable: false,
    draggable: false,
    focusable: false,
  };

  // Floating Agent + MCP nodes above the graph
  const floatY = wrapperTop - FLOAT_GAP - AGENT_H;
  const ssCenterX = (layerBounds.source_systems.minX + layerBounds.source_systems.maxX) / 2;
  const wrapperCenterX = wrapperLeft + wrapperWidth / 2;

  const agentNode: Node = {
    id: '__agent__',
    type: 'agent_node',
    position: { x: ssCenterX - AGENT_W / 2, y: floatY },
    style: { width: AGENT_W, height: AGENT_H },
    data: { label: 'Agent' },
    zIndex: 2,
    selectable: false,
    draggable: false,
    focusable: false,
  };

  const mcpNode: Node = {
    id: '__mcp__',
    type: 'mcp_node',
    position: { x: wrapperCenterX - MCP_W / 2, y: floatY },
    style: { width: MCP_W, height: MCP_H },
    data: { label: 'MCP Server' },
    zIndex: 2,
    selectable: false,
    draggable: false,
    focusable: false,
  };

  // Source Systems box node
  const sourceSysNode: Node = {
    id: 'source_systems_box',
    type: 'source_systems_node',
    position: { x: ssPos.x - SS_W / 2, y: ssPos.y - SS_H / 2 },
    style: { width: SS_W, height: SS_H },
    data: { label: '' },
    zIndex: 1,
    selectable: false,
    draggable: false,
    focusable: false,
  };

  // Lineage nodes
  const nodes: Node[] = effectiveNodeDefs.map((nodeDef) => {
    const pos = dagreGraph.node(nodeDef.id);
    const isSelected = nodeDef.id === selectedNodeId;
    const isHighlighted = nodeDef.highlighted || false;

    // Postgres: MVs → view color, triples → tables color; Materialize/Batch keep originals
    const effectiveType = isPostgres && nodeDef.type === 'mv'
      ? 'view'
      : isPostgres && nodeDef.id === 'triples'
        ? 'tables'
        : nodeDef.type;
    let style = getNodeStyle(effectiveType, isSelected);
    if (isHighlighted && !isSelected && !isPostgres) {
      style = { ...style, border: '3px solid #059669', boxShadow: '0 0 10px rgba(16, 185, 129, 0.4)' };
    }

    return {
      id: nodeDef.id,
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
      data: { label: nodeDef.label },
      style,
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      zIndex: 1,
    };
  });

  // Lineage edges
  const edges: Edge[] = edgeDefs.map((edgeDef, index) => {
    // In batch mode, edges from OLTP (triples) point forward toward their targets;
    // all other non-materialize edges point backward (arrowhead at source end).
    const batchForward = isBatch && edgeDef.source === 'triples';
    return {
      id: `e-${edgeDef.source}-${edgeDef.target}-${index}`,
      source: edgeDef.source,
      target: edgeDef.target,
      style: edgeStyle,
      animated: isMaterialize,
      markerStart: (!isMaterialize && !batchForward)
        ? { type: MarkerType.ArrowClosed, color: '#94a3b8', orient: 'auto-start-reverse' }
        : undefined,
      markerEnd: batchForward
        ? { type: MarkerType.ArrowClosed, color: '#94a3b8' }
        : undefined,
      zIndex: 1,
    };
  });

  // Overlay edges: source systems data flow + agent/MCP interactions
  const overlayEdges: Edge[] = [
    {
      id: 'e-src-triples',
      source: 'source_systems_box',
      target: 'triples',
      sourceHandle: 'right',
      style: edgeStyle,
      animated: isMaterialize,
      markerEnd: isMaterialize ? undefined : { type: MarkerType.ArrowClosed, color: '#94a3b8' },
      zIndex: 1,
    },
    {
      id: 'e-agent-mcp',
      source: '__agent__',
      target: '__mcp__',
      sourceHandle: 'right',
      targetHandle: 'left',
      label: 'Observe',
      style: { stroke: '#6b7280', strokeWidth: 1.5 },
      labelStyle: { fontSize: '12px', fill: '#6b7280', fontWeight: 600 },
      labelBgStyle: { fill: '#f9fafb', fillOpacity: 0.85 },
      animated: false,
      zIndex: 3,
    },
    {
      id: 'e-agent-src',
      source: '__agent__',
      target: 'source_systems_box',
      sourceHandle: 'bottom',
      targetHandle: 'top',
      label: 'Act',
      style: { stroke: '#6b7280', strokeWidth: 1.5 },
      labelStyle: { fontSize: '12px', fill: '#6b7280', fontWeight: 600 },
      labelBgStyle: { fill: '#f9fafb', fillOpacity: 0.85 },
      animated: false,
      zIndex: 3,
    },
    {
      id: 'e-mcp-wrapper',
      source: '__mcp__',
      target: isMaterialize ? '__fgac__' : isBatch ? '__olap__' : '__source_wrapper__',
      sourceHandle: 'bottom',
      targetHandle: 'top',
      style: {
        stroke: isMaterialize ? '#a855f7' : isBatch ? '#d97706' : '#1e40af',
        strokeWidth: 1.5,
        strokeDasharray: '5,3',
      },
      animated: false,
      zIndex: 3,
    },
  ];

  return {
    nodes: [...bandNodes, outerBandNode, agentNode, mcpNode, sourceSysNode, ...nodes],
    edges: [...edges, ...overlayEdges],
  };
}

interface LineageGraphProps {
  selectedNodeId?: string | null;
  onNodeClick?: (nodeId: string) => void;
  scenario?: 'materialize' | 'postgres' | 'batch';
}

export function LineageGraph({ selectedNodeId, onNodeClick, scenario = 'materialize' }: LineageGraphProps) {
  const { nodes, edges } = useMemo(
    () => getLayoutedElements(nodeDefinitions, edgeDefinitions, selectedNodeId, scenario),
    [selectedNodeId, scenario]
  );

  const handleNodeClick: NodeMouseHandler = useCallback(
    (_, node) => {
      if (node.id.startsWith('__') || node.id === 'source_systems_box') return;
      if (onNodeClick) {
        onNodeClick(node.id);
      }
    },
    [onNodeClick]
  );

  return (
    <div className="w-full">
      {/* Graph */}
      <div className="h-[480px] w-full border border-gray-200 rounded-lg bg-gray-50">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodeClick={handleNodeClick}
          fitView
          fitViewOptions={{ padding: 0.15 }}
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

      {/* Legend */}
      <div className="flex flex-wrap gap-x-6 gap-y-2 mt-3 text-sm">
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
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded" style={{ background: nodeColors.tables.bg }} />
          <span className="text-gray-600">Table</span>
        </div>

        {selectedNodeId && (
          <div className="flex items-center gap-2 ml-auto">
            <div className="w-4 h-4 rounded border-2 border-yellow-400" style={{ background: 'transparent' }} />
            <span className="text-gray-600">Selected</span>
          </div>
        )}
      </div>

      {/* Description */}
      <p className="mt-3 text-sm text-gray-500">
        Three data products from the same <span className="font-medium text-blue-600">OLTP source</span>:{' '}
        <span className="font-medium text-green-600">store_inventory_mv</span> (stock levels),{' '}
        <span className="font-medium text-green-600">orders_with_lines_mv</span> (order details), and{' '}
        <span className="font-medium text-green-600">dynamic_pricing_mv</span> (live pricing with 9 factors).
        The agent observes via MCP and acts on source systems. Click any node to view its SQL.
      </p>
    </div>
  );
}

export default LineageGraph;
