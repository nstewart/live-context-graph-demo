import { VectorPipelineCard } from "../components/VectorPipelineCard";

export default function VectorSearchPage() {
  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Freshmart Agent Search Demo</h1>
        <p className="text-sm text-gray-500 mt-1">
          Semantic vector search with live data hydration from Materialize
        </p>
      </div>
      <VectorPipelineCard defaultExpanded />
    </div>
  );
}
