import { useEffect, useState } from "react";
import { Check, Code, Copy, ExternalLink, X } from "lucide-react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import { ViewDefinitionResponse } from "../api/client";
import { aliasView } from "../label";

/** Materialize console. Defaults to the emulator's console port; override with
 *  VITE_MZ_CONSOLE_URL when pointing the demo at Cloud or a tunnelled backend. */
export const MZ_CONSOLE_URL =
  import.meta.env.VITE_MZ_CONSOLE_URL?.trim() || "http://localhost:6874/";

const COPIED_RESET_MS = 2000;

interface ViewDefinitionModalProps {
  /** Node whose definition is shown; the modal renders only when set. */
  viewName: string | null;
  definition: ViewDefinitionResponse | null;
  isLoading: boolean;
  onClose: () => void;
}

const OBJECT_TYPE_LABELS: Record<string, string> = {
  materialized_view: "MATERIALIZED VIEW",
  source: "SOURCE",
  table: "TABLE",
};

/** SHOW CREATE viewer for a clicked lineage-graph node. Shared by the query
 *  statistics page and the agent search demo so both render identically. */
export const ViewDefinitionModal = ({
  viewName,
  definition,
  isLoading,
  onClose,
}: ViewDefinitionModalProps) => {
  const [copied, setCopied] = useState(false);

  // Clear the confirmation on its own, and when switching to another node
  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), COPIED_RESET_MS);
    return () => clearTimeout(timer);
  }, [copied]);

  useEffect(() => setCopied(false), [viewName]);

  if (!viewName) return null;

  const objectType = OBJECT_TYPE_LABELS[definition?.object_type ?? ''] ?? 'VIEW';
  const showCommand = `SHOW CREATE ${objectType} ${viewName};`;

  const copyShowCommand = async () => {
    try {
      await navigator.clipboard.writeText(showCommand);
      setCopied(true);
    } catch (err) {
      // Clipboard is unavailable over plain http on some hosts; the command is
      // on screen either way, so this is a convenience, not a dead end.
      console.error("Failed to copy SHOW command:", err);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      {/* Modal */}
      <div className="relative bg-gray-900 rounded-lg overflow-hidden w-full max-w-4xl max-h-[80vh] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="px-4 py-3 bg-gray-800 border-b border-gray-700 flex-shrink-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Code className="h-4 w-4 text-yellow-400" />
              <span className="text-sm font-medium text-gray-200">
                View Definition
                {viewName && (
                  <span className="ml-2 font-mono text-xs text-gray-400">
                    {aliasView(viewName)}
                  </span>
                )}
              </span>
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-200 transition-colors"
              title="Close"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
          <div className="mt-2 flex items-center justify-between gap-3">
            {/* The real object name, not the label's. This statement is meant
                to be copied into the SQL shell, so aliasing it would name an
                object that does not exist. label-lint-ok: runnable SQL */}
            <div className="font-mono text-xs text-gray-400">
              <span className="text-purple-400">SHOW CREATE</span>{' '}
              <span className="text-blue-400">{objectType}</span>{' '}
              <span className="text-green-400">{viewName}</span>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                onClick={copyShowCommand}
                title={`Copy "${showCommand}"`}
                className="flex items-center gap-1 px-2 py-1 rounded text-xs text-gray-300 bg-gray-700 hover:bg-gray-600 transition-colors"
              >
                {copied ? (
                  <>
                    <Check className="h-3.5 w-3.5 text-green-400" />
                    Copied
                  </>
                ) : (
                  <>
                    <Copy className="h-3.5 w-3.5" />
                    Copy SHOW
                  </>
                )}
              </button>
              <a
                href={MZ_CONSOLE_URL}
                target="_blank"
                rel="noopener noreferrer"
                title="Open the Materialize console SQL shell in a new tab"
                className="flex items-center gap-1 px-2 py-1 rounded text-xs text-gray-300 bg-gray-700 hover:bg-gray-600 transition-colors"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                SQL Shell
              </a>
            </div>
          </div>
        </div>
        {/* SQL Content */}
        <div className="flex-1 overflow-auto p-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-6 w-6 border-2 border-gray-600 border-t-yellow-400"></div>
            </div>
          ) : definition ? (
            <SyntaxHighlighter
              language="sql"
              style={vscDarkPlus}
              customStyle={{
                margin: 0,
                padding: 0,
                background: 'transparent',
                fontSize: '0.875rem',
              }}
              wrapLongLines={true}
            >
              {definition.sql}
            </SyntaxHighlighter>
          ) : (
            <pre className="text-xs font-mono text-gray-500">Failed to load view definition</pre>
          )}
        </div>
      </div>
    </div>
  );
};
