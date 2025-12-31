import { useState, useEffect, useRef } from "react";

interface HighlightedJsonProps {
  data: object;
  trackingKey?: string;
}

/**
 * JSON viewer component that highlights changed values with a yellow glow.
 * Useful for showing real-time data updates.
 */
export const HighlightedJson = ({ data, trackingKey }: HighlightedJsonProps) => {
  const prevDataRef = useRef<string>("");
  const prevTrackingKeyRef = useRef<string | undefined>(undefined);
  const changedPathsRef = useRef<Map<string, number>>(new Map());
  const [, forceUpdate] = useState(0);

  const HIGHLIGHT_DURATION = 1500; // ms

  // Find changed paths by comparing JSON
  useEffect(() => {
    // Reset when tracking key changes (e.g., different order selected)
    if (trackingKey !== prevTrackingKeyRef.current) {
      prevTrackingKeyRef.current = trackingKey;
      prevDataRef.current = JSON.stringify(data);
      changedPathsRef.current = new Map();
      return;
    }

    const currentJson = JSON.stringify(data);
    if (prevDataRef.current && prevDataRef.current !== currentJson) {
      // Find which paths changed
      const prevData = JSON.parse(prevDataRef.current);
      const now = Date.now();

      const findChanges = (current: unknown, previous: unknown, path: string) => {
        if (typeof current !== typeof previous) {
          changedPathsRef.current.set(path, now);
          return;
        }
        if (current === null || previous === null) {
          if (current !== previous) changedPathsRef.current.set(path, now);
          return;
        }
        if (typeof current !== "object") {
          if (current !== previous) changedPathsRef.current.set(path, now);
          return;
        }
        if (Array.isArray(current) && Array.isArray(previous)) {
          if (current.length !== previous.length) {
            changedPathsRef.current.set(path, now);
          }
          current.forEach((item, i) => {
            findChanges(item, previous[i], `${path}[${i}]`);
          });
          return;
        }
        const currentObj = current as Record<string, unknown>;
        const previousObj = previous as Record<string, unknown>;
        const allKeys = new Set([
          ...Object.keys(currentObj),
          ...Object.keys(previousObj),
        ]);
        allKeys.forEach((key) => {
          findChanges(
            currentObj[key],
            previousObj[key],
            path ? `${path}.${key}` : key
          );
        });
      };

      findChanges(data, prevData, "");
      forceUpdate((n) => n + 1);

      // Schedule cleanup of expired highlights
      const timer = setTimeout(() => {
        const now = Date.now();
        for (const [path, timestamp] of changedPathsRef.current) {
          if (now - timestamp >= HIGHLIGHT_DURATION) {
            changedPathsRef.current.delete(path);
          }
        }
        forceUpdate((n) => n + 1);
      }, HIGHLIGHT_DURATION);

      prevDataRef.current = currentJson;
      return () => clearTimeout(timer);
    }
    prevDataRef.current = currentJson;
  }, [data, trackingKey]);

  // Check if a path is currently highlighted
  const isHighlighted = (path: string): boolean => {
    const timestamp = changedPathsRef.current.get(path);
    if (!timestamp) return false;
    return Date.now() - timestamp < HIGHLIGHT_DURATION;
  };

  // Render JSON with highlights
  const renderValue = (
    value: unknown,
    path: string,
    indent: number
  ): React.ReactNode => {
    const isChanged = isHighlighted(path);
    const glowClass = isChanged
      ? "animate-pulse bg-yellow-500/30 rounded px-1 -mx-1"
      : "";
    const spaces = "  ".repeat(indent);

    if (value === null) {
      return <span className={`text-gray-500 ${glowClass}`}>null</span>;
    }
    if (typeof value === "boolean") {
      return (
        <span className={`text-purple-400 ${glowClass}`}>
          {value ? "true" : "false"}
        </span>
      );
    }
    if (typeof value === "number") {
      return <span className={`text-blue-400 ${glowClass}`}>{value}</span>;
    }
    if (typeof value === "string") {
      return <span className={`text-green-400 ${glowClass}`}>"{value}"</span>;
    }
    if (Array.isArray(value)) {
      if (value.length === 0) return <span className={glowClass}>[]</span>;
      return (
        <>
          {"[\n"}
          {value.map((item, i) => (
            <span key={i}>
              {spaces} {renderValue(item, `${path}[${i}]`, indent + 1)}
              {i < value.length - 1 ? "," : ""}
              {"\n"}
            </span>
          ))}
          {spaces}
          {"]"}
        </>
      );
    }
    if (typeof value === "object") {
      const entries = Object.entries(value as Record<string, unknown>);
      if (entries.length === 0) return <span className={glowClass}>{"{}"}</span>;
      return (
        <>
          {"{\n"}
          {entries.map(([key, val], i) => {
            const keyPath = path ? `${path}.${key}` : key;
            const isKeyChanged = isHighlighted(keyPath);
            const keyGlowClass = isKeyChanged
              ? "animate-pulse bg-yellow-500/30 rounded px-1 -mx-1"
              : "";
            return (
              <span key={key}>
                {spaces}{" "}
                <span className={`text-gray-400 ${keyGlowClass}`}>"{key}"</span>:{" "}
                {renderValue(val, keyPath, indent + 1)}
                {i < entries.length - 1 ? "," : ""}
                {"\n"}
              </span>
            );
          })}
          {spaces}
          {"}"}
        </>
      );
    }
    return String(value);
  };

  return (
    <pre className="text-xs font-mono text-gray-300 whitespace-pre">
      {renderValue(data, "", 0)}
    </pre>
  );
};

export default HighlightedJson;
