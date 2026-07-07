import { useEffect, useRef } from "react";
import { API, fetchLiveIoSettings, postMidiInEvent } from "../api";

type OscTarget = {
  node_id: string;
  param: string;
};

type Props = {
  enabled: boolean;
  onOscWidget: (target: OscTarget, value: number) => void;
};

function midiEventFromMessage(message: MIDIMessageEvent): Record<string, unknown> | null {
  const data = message.data;
  if (!data || data.length < 2) return null;
  const status = data[0];
  const channel = (status & 0x0f) + 1;
  const command = status & 0xf0;
  if (command === 0xb0 && data.length >= 3) {
    return { type: "cc", channel, num: data[1], value: data[2] / 127 };
  }
  if (command === 0x90 && data.length >= 3) {
    return {
      type: data[2] === 0 ? "note_off" : "note_on",
      channel,
      note: data[1],
      velocity: data[2] / 127,
    };
  }
  return null;
}

export function useLiveIo({ enabled, onOscWidget }: Props) {
  const deviceIdRef = useRef<string>("virtual:in-demo");

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let access: MIDIAccess | null = null;
    const ws = new WebSocket(`${API.replace(/^http/, "ws")}/api/ws/midi/in`);

    const setup = async () => {
      const settings = await fetchLiveIoSettings();
      if (cancelled) return;
      deviceIdRef.current = settings.default_input_id ?? "virtual:in-demo";

      if (settings.midi_input_enabled && navigator.requestMIDIAccess) {
        try {
          access = await navigator.requestMIDIAccess();
          for (const input of access.inputs.values()) {
            input.onmidimessage = (message) => {
              const event = midiEventFromMessage(message);
              if (!event) return;
              if (ws.readyState === WebSocket.OPEN) {
                ws.send(
                  JSON.stringify({
                    type: "midi.event",
                    device_id: deviceIdRef.current,
                    event,
                  }),
                );
              } else {
                void postMidiInEvent(deviceIdRef.current, event);
              }
            };
          }
        } catch {
          // Web MIDI unavailable — virtual demo capture still works at render time
        }
      }
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type !== "osc.message" || !msg.target) return;
        const args = msg.args as unknown[];
        const value = typeof args[0] === "number" ? args[0] : Number(args[0]);
        if (!Number.isFinite(value)) return;
        onOscWidget(msg.target as OscTarget, value);
      } catch {
        // ignore malformed messages
      }
    };

    void setup();
    return () => {
      cancelled = true;
      if (access) {
        for (const input of access.inputs.values()) {
          input.onmidimessage = null;
        }
      }
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
    };
  }, [enabled, onOscWidget]);
}
