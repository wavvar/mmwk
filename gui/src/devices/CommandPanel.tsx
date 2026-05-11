type CommandPanelProps = {
  title: string;
  commands: string[];
};

export default function CommandPanel({ title, commands }: CommandPanelProps) {
  return (
    <section className="command-panel">
      <h4>{title}</h4>
      <div className="command-button-grid">
        {commands.map((command) => (
          <button key={command} type="button">
            {command}
          </button>
        ))}
      </div>
    </section>
  );
}
