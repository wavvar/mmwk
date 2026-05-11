import DeviceList from "./devices/DeviceList";
import ServerProfiles from "./servers/ServerProfiles";

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
        <div className="workspace-grid">
          <DeviceList />
          <ServerProfiles />
        </div>
      </section>
    </main>
  );
}

export default App;
