import type { DeviceProfile, ServerProfile } from "../app/backend";

type DeviceEditorProps = {
  servers: ServerProfile[];
  onSave: (profile: DeviceProfile) => void | Promise<void>;
};

function defaultProfile(serverId: string | null): DeviceProfile {
  return {
    id: "new-device",
    name: "",
    profile: "bridge",
    transport: "mqtt",
    mqtt_server_profile_id: serverId,
    mqtt_prod: "mmwk",
    mqtt_oid: "mmwk",
    mqtt_did: "",
    mqtt_cid: "",
    sidecar: null
  };
}

export default function DeviceEditor({ servers, onSave }: DeviceEditorProps) {
  const profile = defaultProfile(servers[0]?.id ?? null);

  return (
    <form
      className="stack-form"
      onSubmit={(event) => {
        event.preventDefault();
        void onSave(profile);
      }}
    >
      <label>
        Device Name
        <input defaultValue={profile.name} name="name" placeholder="Lab bridge" />
      </label>
      <label>
        Device Profile
        <select defaultValue={profile.profile} name="profile">
          <option value="bridge">Bridge</option>
          <option value="hub">Hub</option>
        </select>
      </label>
      <label>
        Server Profile
        <select defaultValue={profile.mqtt_server_profile_id ?? ""} name="server">
          <option value="">Direct device connection</option>
          {servers.map((server) => (
            <option key={server.id} value={server.id}>
              {server.name}
            </option>
          ))}
        </select>
      </label>
      <button className="secondary-action" type="submit">
        Save Device
      </button>
    </form>
  );
}
