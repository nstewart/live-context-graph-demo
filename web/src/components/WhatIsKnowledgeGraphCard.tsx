import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { OntologyGraph } from "./OntologyGraph";

export const WhatIsKnowledgeGraphCard = () => {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="bg-white rounded-lg shadow mb-6">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full p-4 flex items-center justify-between hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-2">
          {isExpanded ? (
            <ChevronDown className="h-5 w-5 text-gray-500" />
          ) : (
            <ChevronRight className="h-5 w-5 text-gray-500" />
          )}
          <div className="text-left">
            <h3 className="text-lg font-semibold text-gray-900">Leveraging Context Graphs</h3>
            <p className="text-xs text-gray-500">
              The relationships that give agents and humans understanding about what to do next and why
            </p>
          </div>
        </div>
      </button>

      {isExpanded && (
        <div className="px-6 pb-6">
          {/* Explainer text */}
          <div className="mb-4 text-sm text-gray-600 leading-relaxed space-y-2">
            <p>
              A <span className="font-medium">knowledge graph</span> (or ontology) defines the
              structure that sits on top of raw triples. It specifies which{" "}
              <span className="font-medium">entity types</span> exist (Order, Customer, Product),
              what <span className="font-medium">properties</span> each type can have, and how
              entities <span className="font-medium">relate</span> to one another.
            </p>
            <p>
              For AI agents, the knowledge graph becomes a context graph, which is always available
              and serves as a trusted map: it tells them what kinds of facts exist in the system,
              which updates are valid, and how to traverse relationships to gather context. Without
              this schema, triples are just disconnected facts&mdash;with it, agents can reason
              about the domain and make informed decisions. In production, agents log their
              decisions as triples, which can also update the edges of the context graph live.
            </p>
          </div>

          {/* Schema Visualization */}
          <OntologyGraph />
        </div>
      )}
    </div>
  );
};

export default WhatIsKnowledgeGraphCard;
