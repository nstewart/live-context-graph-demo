import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { LineageGraph } from "./LineageGraph";
import { ViewDefinitionModal } from "./ViewDefinitionModal";
import { useViewDefinitionSelection } from "../hooks/useViewDefinitions";

interface ReferenceArchitectureCardProps {
  defaultExpanded?: boolean;
}

/** The Materialize reference architecture, fixed — no scenario toggle.
 *
 *  Draws the live medallion stack over the triple-store source shape: agent
 *  writes land directly in the triple store, which feeds the canonical views
 *  the agent reads back. Nodes are clickable and show their SHOW CREATE. */
export const ReferenceArchitectureCard = ({
  defaultExpanded = false,
}: ReferenceArchitectureCardProps) => {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const { selectedNodeId, definition, isLoading, onNodeClick, close } =
    useViewDefinitionSelection();

  return (
    <>
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
              <h3 className="text-lg font-semibold text-gray-900">
                Live context layer for agents and apps
              </h3>
              <p className="text-xs text-gray-500">
                The context layer is made up of canonical views that represent the core "nouns" of
                the agent's world model. You can think of these as data products or named datasets
                that are maintained and exposed for consumption by agents and applications. Unlike a
                one-off query, they are designed to be discoverable, reusable, and composable across
                teams and services.
              </p>
            </div>
          </div>
        </button>
        {isExpanded && (
          <div className="p-6 pt-0">
            <h4 className="text-sm font-semibold text-gray-700 mb-2">
              Context maintained proactively via live medallion architecture
            </h4>
            <LineageGraph
              selectedNodeId={selectedNodeId}
              onNodeClick={onNodeClick}
              scenario="materialize_triples"
            />
          </div>
        )}
      </div>

      <ViewDefinitionModal
        viewName={selectedNodeId}
        definition={definition}
        isLoading={isLoading}
        onClose={close}
      />
    </>
  );
};
