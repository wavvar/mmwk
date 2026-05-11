const rows = [
  { device: "Bridge", bytes: 0, messages: 0, rate: "0 B/s" },
  { device: "Hub", bytes: 0, messages: 0, rate: "0 B/s" }
];

export default function CollectionBench() {
  return (
    <section className="workspace-panel console-panel" aria-label="Raw collection">
      <div className="panel-heading">
        <h3>Raw Collection</h3>
        <span>0 active</span>
      </div>
      <div className="collection-toolbar">
        <button className="primary-action" type="button">
          Start
        </button>
        <button className="secondary-action" type="button">
          Stop
        </button>
      </div>
      <div className="metrics-table">
        <div className="metrics-row metrics-head">
          <span>Device</span>
          <span>Bytes</span>
          <span>Messages</span>
          <span>Rate</span>
        </div>
        {rows.map((row) => (
          <div className="metrics-row" key={row.device}>
            <strong>{row.device}</strong>
            <span>{row.bytes}</span>
            <span>{row.messages}</span>
            <span>{row.rate}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
