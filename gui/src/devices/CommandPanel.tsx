import { useState } from "react";
import { executeDeviceCommand } from "../app/backend";

export type CommandSpec = {
  label: string;
  commandId: string;
  destructive?: boolean;
};

type CommandPanelProps = {
  title: string;
  commands: CommandSpec[];
  deviceProfileId?: string | null;
};

export default function CommandPanel({ title, commands, deviceProfileId }: CommandPanelProps) {
  const [busyCommand, setBusyCommand] = useState<string | null>(null);

  return (
    <section className="command-panel">
      <h4>{title}</h4>
      <div className="command-button-grid">
        {commands.map((command) => (
          <button
            disabled={!deviceProfileId || busyCommand === command.commandId}
            key={`${command.commandId}:${command.label}`}
            onClick={() => {
              if (!deviceProfileId) {
                return;
              }
              setBusyCommand(command.commandId);
              void executeDeviceCommand({
                device_profile_id: deviceProfileId,
                command_id: command.commandId,
                args: {},
                confirmation: command.destructive
                  ? "EXECUTE_DESTRUCTIVE_COMMAND"
                  : undefined,
                key: undefined
              }).finally(() => setBusyCommand(null));
            }}
            type="button"
          >
            {command.label}
          </button>
        ))}
      </div>
    </section>
  );
}
