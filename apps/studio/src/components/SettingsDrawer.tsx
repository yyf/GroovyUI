import { useCallback, useEffect, useState } from "react";
import {
  fetchAudioDevices,
  fetchLiveIoSettings,
  fetchMidiDevices,
  updateLiveIoSettings,
  type AudioDevice,
  type LiveIoSettings,
  type MidiDevice,
} from "../api";

type Props = {
  open: boolean;
  onClose: () => void;
};

function deviceLabel(device: AudioDevice | MidiDevice): string {
  if ("channels" in device && device.channels > 0) {
    const rate = Math.round(device.sample_rate);
    return `${device.name} (${device.manufacturer}, ${device.channels} ch @ ${rate} Hz)`;
  }
  if (device.manufacturer) return `${device.name} (${device.manufacturer})`;
  return device.name;
}

export default function SettingsDrawer({ open, onClose }: Props) {
  const [settings, setSettings] = useState<LiveIoSettings | null>(null);
  const [audioInputs, setAudioInputs] = useState<AudioDevice[]>([]);
  const [audioOutputs, setAudioOutputs] = useState<AudioDevice[]>([]);
  const [midiInputs, setMidiInputs] = useState<MidiDevice[]>([]);
  const [midiOutputs, setMidiOutputs] = useState<MidiDevice[]>([]);
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    const warnings: string[] = [];
    try {
      const liveSettings = await fetchLiveIoSettings();
      setSettings(liveSettings);

      const [inAudio, outAudio, inMidi, outMidi] = await Promise.all([
        fetchAudioDevices("in").catch(() => {
          warnings.push("Audio input devices unavailable");
          return [] as AudioDevice[];
        }),
        fetchAudioDevices("out").catch(() => {
          warnings.push("Audio output devices unavailable");
          return [] as AudioDevice[];
        }),
        fetchMidiDevices("in").catch(() => {
          warnings.push("MIDI input devices unavailable");
          return [] as MidiDevice[];
        }),
        fetchMidiDevices("out").catch(() => {
          warnings.push("MIDI output devices unavailable");
          return [] as MidiDevice[];
        }),
      ]);
      setAudioInputs(inAudio);
      setAudioOutputs(outAudio);
      setMidiInputs(inMidi);
      setMidiOutputs(outMidi);
      setStatus(warnings.length ? warnings.join(". ") : "");
    } catch {
      setSettings(null);
      setStatus("Could not load settings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    void refresh();
  }, [open, refresh]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const save = async (patch: Partial<LiveIoSettings>) => {
    try {
      const next = await updateLiveIoSettings(patch);
      setSettings(next);
      setStatus("Saved");
    } catch {
      setStatus("Could not save settings");
    }
  };

  if (!open) return null;

  return (
    <div className="compliance-backdrop" onClick={onClose}>
      <aside className="compliance-drawer settings-drawer" onClick={(e) => e.stopPropagation()}>
        <header>
          <h2>Settings</h2>
          <button type="button" onClick={onClose}>
            Close
          </button>
        </header>
        <div className="compliance-body">
          {loading && !settings ? <p className="compliance-hint">Loading settings…</p> : null}
          {!loading && !settings ? (
            <div className="settings-error">
              <p className="compliance-hint">{status || "Could not load settings."}</p>
              <button type="button" onClick={() => void refresh()}>
                Retry
              </button>
            </div>
          ) : null}
          {settings ? (
            <>
              <section className="settings-section">
                <h3>Audio I/O</h3>
                <p className="compliance-hint">
                  Opt-in audio capture and playback drivers. Device listing uses the local PortAudio
                  stack when available; virtual devices are always available for preview routing.
                </p>
                <label className="settings-row">
                  <input
                    type="checkbox"
                    checked={settings.audio_input_enabled}
                    onChange={(e) => void save({ audio_input_enabled: e.target.checked })}
                  />
                  Enable audio input
                </label>
                <label className="settings-row">
                  <input
                    type="checkbox"
                    checked={settings.audio_output_enabled}
                    onChange={(e) => void save({ audio_output_enabled: e.target.checked })}
                  />
                  Enable audio output
                </label>
                <label className="settings-field">
                  Input driver
                  <select
                    value={settings.default_audio_input_id ?? ""}
                    onChange={(e) => void save({ default_audio_input_id: e.target.value })}
                  >
                    {audioInputs.map((device) => (
                      <option key={device.id} value={device.id}>
                        {deviceLabel(device)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="settings-field">
                  Output driver
                  <select
                    value={settings.default_audio_output_id ?? ""}
                    onChange={(e) => void save({ default_audio_output_id: e.target.value })}
                  >
                    {audioOutputs.map((device) => (
                      <option key={device.id} value={device.id}>
                        {deviceLabel(device)}
                      </option>
                    ))}
                  </select>
                </label>
              </section>

              <section className="settings-section">
                <h3>Live I/O</h3>
                <p className="compliance-hint">
                  Hardware MIDI and OSC are opt-in. OSC binds localhost only; addresses must start
                  with <code>/groovy/</code>.
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
                  MIDI input
                  <select
                    value={settings.default_input_id ?? ""}
                    onChange={(e) => void save({ default_input_id: e.target.value })}
                  >
                    {midiInputs.map((device) => (
                      <option key={device.id} value={device.id}>
                        {deviceLabel(device)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="settings-field">
                  MIDI output
                  <select
                    value={settings.default_output_id ?? ""}
                    onChange={(e) => void save({ default_output_id: e.target.value })}
                  >
                    {midiOutputs.map((device) => (
                      <option key={device.id} value={device.id}>
                        {deviceLabel(device)}
                      </option>
                    ))}
                  </select>
                </label>
              </section>

              <button type="button" onClick={() => void refresh()}>
                Refresh devices
              </button>
            </>
          ) : null}
          {status && settings ? (
            <p className={`settings-status${status === "Saved" ? "" : " settings-status--warn"}`}>{status}</p>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
