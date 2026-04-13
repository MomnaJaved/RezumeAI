import { useState } from "react";
import { classifyRole } from "../api";

export default function PlaygroundPage() {
  const [text, setText] = useState("");
  const [out, setOut] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function run() {
    setLoading(true);
    setOut(null);
    try {
      const r = await classifyRole(text);
      setOut(JSON.stringify(r, null, 2));
    } catch (e) {
      setOut((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <h1>Role classification</h1>
      <p className="muted">POST body: <code>{`{ "resume_text": "..." }`}</code></p>
      <label htmlFor="resume">Resume text</label>
      <textarea id="resume" rows={10} value={text} onChange={(e) => setText(e.target.value)} />
      <div style={{ marginTop: "0.75rem" }}>
        <button type="button" className="primary" disabled={loading || !text.trim()} onClick={() => void run()}>
          Classify
        </button>
      </div>
      {out ? (
        <pre className="card" style={{ marginTop: "1rem", overflow: "auto" }}>
          {out}
        </pre>
      ) : null}
    </div>
  );
}
