const deviceGroups = [
  "Device Profiles",
  "Shared Servers",
  "Bridge Console",
  "Hub Events",
  "Collection Runs"
];

function App() {
  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Workspace">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            M
          </span>
          <div>
            <h1>MMWK Desktop</h1>
            <p>Local device operations</p>
          </div>
        </div>
        <nav>
          {deviceGroups.map((group) => (
            <button className="nav-button" key={group} type="button">
              {group}
            </button>
          ))}
        </nav>
      </aside>
      <section className="workspace" aria-label="MMWK device workspace">
        <header className="workspace-header">
          <div>
            <h2>Device And Server Workspace</h2>
            <p>Profiles, embedded services, collection, and hub event review.</p>
          </div>
          <button className="primary-action" type="button">
            Add Device
          </button>
        </header>
        <div className="panel-grid">
          <section className="panel">
            <h3>Connection Profiles</h3>
            <p>Manage serial and MQTT profiles for bridge and hub devices.</p>
          </section>
          <section className="panel">
            <h3>Embedded Services</h3>
            <p>Run local MMWK-scoped MQTT and HTTP services from the desktop app.</p>
          </section>
          <section className="panel">
            <h3>Hub Event Logs</h3>
            <p>Record, count, filter, and replay events received from hub devices.</p>
          </section>
        </div>
      </section>
    </main>
  );
}

export default App;
