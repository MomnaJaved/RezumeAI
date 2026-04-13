export default function PlaceholderPage({ title, note }: { title: string; note?: string }) {
  return (
    <div>
      <h1>{title}</h1>
      <p className="muted">{note ?? "This section is coming next."}</p>
    </div>
  );
}

