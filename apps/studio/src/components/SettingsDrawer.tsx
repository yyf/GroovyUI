import { useCallback, useEffect, useState } from "react";
import {
  fetchAudioDevices,
  fetchLiveIoSettings,
  fetchMidiDevices,
  fetchStudioSettings,
  updateLiveIoSettings,
  updateStudioSettings,
  type AudioDevice,
  type LiveIoSettings,
  type MidiDevice,
  type StudioSettings,
} from "../api";
import { ParamSwitch } from "./ParamControls";

/** Kept for Phase 4 Live I/O — not mounted in App until device routing ships. */
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
  const [studioSettings, setStudioSettings] = useState<StudioSettings | null>(null);
  const [hfTokenDraft, setHfTokenDraft] = useState("");
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
      const studio = await fetchStudioSettings().catch(() => null);
      setStudioSettings(studio);
      setHfTokenDraft("");

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

  const saveStudio = async (patch: { hf_token?: string | null }) => {
    try {
      const next = await updateStudioSettings(patch);
      setStudioSettings(next);
      setHfTokenDraft("");
      setStatus("Saved");
    } catch {
      setStatus("Could not save studio settings");
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
                <div className="settings-row">
                  <ParamSwitch
                    checked={settings.audio_input_enabled}
                    onChange={(checked) => void save({ audio_input_enabled: checked })}
                  />
                  <span>Enable audio input</span>
                </div>
                <div className="settings-row">
                  <ParamSwitch
                    checked={settings.audio_output_enabled}
                    onChange={(checked) => void save({ audio_output_enabled: checked })}
                  />
                  <span>Enable audio output</span>
                </div>
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
                <div className="settings-row">
                  <ParamSwitch
                    checked={settings.midi_input_enabled}
                    onChange={(checked) => void save({ midi_input_enabled: checked })}
                  />
                  <span>Enable MIDI input</span>
                </div>
                <div className="settings-row">
                  <ParamSwitch
                    checked={settings.midi_output_enabled}
                    onChange={(checked) => void save({ midi_output_enabled: checked })}
                  />
                  <span>Enable MIDI output</span>
                </div>
                <div className="settings-row">
                  <ParamSwitch
                    checked={settings.osc_live_enabled}
                    onChange={(checked) => void save({ osc_live_enabled: checked })}
                  />
                  <span>Enable live OSC (UDP :9000 + POST /api/osc/in)</span>
                </div>
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

              <section className="settings-section">
                <h3>Model installs</h3>
                <p className="compliance-hint">
                  Hugging Face token for gated model weights. Environment variable <code>HF_TOKEN</code> takes
                  precedence over this field.
                </p>
                {studioSettings?.hf_token_source === "environment" ? (
                  <p className="compliance-hint">Using HF_TOKEN from environment.</p>
                ) : studioSettings?.hf_token_set ? (
                  <p className="compliance-hint">Token saved in project settings.</p>
                ) : (
                  <p className="compliance-hint">No token configured — gated downloads may fail.</p>
                )}
                <label className="settings-field">
                  HF token
                  <input
                    type="password"
                    autoComplete="off"
                    placeholder={studioSettings?.hf_token_set ? "••••••••  (leave blank to keep)" : "hf_…"}
                    value={hfTokenDraft}
                    onChange={(event) => setHfTokenDraft(event.target.value)}
                  />
                </label>
                <div className="model-card__actions">
                  <button
                    type="button"
                    disabled={!hfTokenDraft.trim()}
                    onClick={() => void saveStudio({ hf_token: hfTokenDraft.trim() })}
                  >
                    Save token
                  </button>
                  {studioSettings?.hf_token_set && studioSettings.hf_token_source !== "environment" ? (
                    <button type="button" onClick={() => void saveStudio({ hf_token: null })}>
                      Clear token
                    </button>
                  ) : null}
                </div>
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
