import { useEffect, useRef } from 'react';

interface LogViewerProps {
  log: string;
  autoScroll?: boolean;
}

export function LogViewer({ log, autoScroll = true }: LogViewerProps) {
  const containerRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [log, autoScroll]);

  if (!log) {
    return (
      <div className="log-viewer log-viewer-empty">
        No log output yet...
      </div>
    );
  }

  return (
    <pre ref={containerRef} className="log-viewer">
      {log}
    </pre>
  );
}
