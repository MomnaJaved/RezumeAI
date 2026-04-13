import { useEffect, useRef, useState } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { pdfjsLib } from "../pdfjsSetup";

function PdfPageCanvas({
  pdf,
  pageNum,
  scale,
}: {
  pdf: PDFDocumentProxy;
  pageNum: number;
  scale: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const page = await pdf.getPage(pageNum);
      const viewport = page.getViewport({ scale });
      const canvas = canvasRef.current;
      if (!canvas || cancelled) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      const task = page.render({ canvasContext: ctx, viewport });
      await task.promise;
    })();
    return () => {
      cancelled = true;
    };
  }, [pdf, pageNum, scale]);

  return <canvas ref={canvasRef} className="cand-preview-pdf-page" />;
}

/**
 * Renders a PDF to canvases (works in Safari, embedded browsers, etc.).
 * Blob/iframes often fail outside Chrome.
 */
export default function ResumePdfJsView({ data }: { data: ArrayBuffer }) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setPdf(null);
    setErr(null);
    (async () => {
      try {
        // pdf.js may transfer the underlying buffer to a worker and detach it — always pass a copy.
        const copy = data.byteLength ? data.slice(0) : data;
        const loadingTask = pdfjsLib.getDocument({ data: new Uint8Array(copy), verbosity: 0 });
        const doc = await loadingTask.promise;
        if (!cancelled) setPdf(doc);
      } catch (e) {
        if (!cancelled) setErr((e as Error).message || "Could not parse PDF.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [data]);

  if (err) {
    return (
      <p className="muted cand-preview-fallback" style={{ margin: "1.5rem auto", textAlign: "center" }}>
        {err}
      </p>
    );
  }

  if (!pdf) {
    return (
      <p className="muted cand-preview-fallback" style={{ margin: "2rem auto" }}>
        Rendering PDF…
      </p>
    );
  }

  const scale =
    typeof window !== "undefined" && window.innerWidth < 640
      ? 1.05
      : typeof window !== "undefined" && window.innerWidth < 900
        ? 1.2
        : 1.35;

  return (
    <div className="cand-preview-pdfjs">
      {Array.from({ length: pdf.numPages }, (_, i) => (
        <PdfPageCanvas key={i + 1} pdf={pdf} pageNum={i + 1} scale={scale} />
      ))}
    </div>
  );
}
