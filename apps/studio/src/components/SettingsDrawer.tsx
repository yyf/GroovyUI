import { useCallback, useEffect, useState } from "react";
import {
  fetchLiveIoSettings,
  fetchMidiDevices,
  updateLiveIoSettings,
  type LiveIoSettings,
  type MidiDevice,
} from "../api";

type Props = {
  open: boolean;
  onClose: () => void;
};

export default function SettingsDrawer({ open, onClose }: Props) {
  const [settings, setSettings] = useState<LiveIoSettings | null>(null);
  const [inputs, setInputs] = useState<MidiDevice[]>([]);
  const [outputs, setOutputs] = useState<MidiDevice[]>([]);
  const [status, setStatus] = useState("");

  const refresh = useCallback(async () => {
    const [liveSettings, inDevices, outDevices] = await Promise.all([
      fetchLiveIoSettings(),
      fetchMidiDevices("in"),
      fetchMidiDevices("out"),
    ]);
    setSettings(liveSettings);
    setInputs(inDevices);
    setOutputs(outDevices);
  }, []);

  useEffect(() => {
    if (!open) return;
    refresh().catch(() => setStatus("Could not load live I/O settings"));
  }, [open, refresh]);

  const save = async (patch: Partial<LiveIoSettings>) => {
    const next = await updateLiveIoSettings(patch);
    setSettings(next);
    setStatus("Saved");
  };

  if (!open || !settings) return null;

  return (
    <>
      <div className="compliance-backdrop" onClick={onClose} />
      <aside className="compliance-drawer settings-drawer" onClick={(e) => e.stopPropagation()}>
        <header>
          <h2>Settings</h2>
          <button type="button" onClick={onClose}>
            Close
          </button>
        </header>
        <div className="compliance-body">
          <h3>Live I/O</h3>
          <p className="compliance-hint">
            Hardware MIDI and OSC are opt-in. OSC binds localhost only; addresses must start with{" "}
            <code>/groovy/</code>.
          </p>
          <label className="settings-row">
            <input
              type="checkbox"
              checked={settings.midi_input_enabled}
              onChange={(e) => void save({ midi_input_enabled: e.target.checked })}
            />
            Enable MIDI input
          </label>
          <label className="settings-row">
            <input
              type="checkbox"
              checked={settings.midi_output_enabled}
              onChange={(e) => void save({ midi_output_enabled: e.target.checked })}
            />
            Enable MIDI output
          </label>
          <label className="settings-row">
            <input
              type="checkbox"
              checked={settings.osc_live_enabled}
              onChange={(e) => void save({ osc_live_enabled: e.target.checked })}
            />
            Enable live OSC (UDP :9000 + POST /api/osc/in)
          </label>
          <label className="settings-field">
            Default MIDI input
            <select
              value={settings.default_input_id ?? ""}
              onChange={(e) => void save({ default_input_id: e.target.value })}
            >
              {inputs.map((device) => (
                <option key={device.id} value={device.id}>
                  {device.name}
                </option>
              ))}
            </select>
          </label>
          <label className="settings-field">
            Default MIDI output
            <select
              value={settings.default_output_id ?? ""}
              onChange={(e) => void save({ default_output_id: e.target.value })}
            >
              {outputs.map((device) => (
                <option key={device.id} value={device.id}>
                  {device.name}
                </option>
              ))}
            </select>
          </label>
          <button type="button" onClick={() => void refresh()}>
            Refresh devices
          </button>
          {status ? <p className="settings-status">{status}</p> : null}
        </div>
      </aside>
    </>
  );
}
