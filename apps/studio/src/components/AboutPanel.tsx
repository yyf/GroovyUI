export const STUDIO_VERSION = "0.18.0";

const DEVELOPER_URL = "https://onesystemics.com/";

/** About content for the Inspector (replaces the old popup window). */
export default function AboutPanel() {
  return (
    <aside className="node-helper node-helper--about" aria-label="About GroovyUI">
      <header className="node-helper__header">
        <h2>GroovyUI Studio</h2>
        <span className="node-helper__id">v{STUDIO_VERSION}</span>
      </header>
      <div className="node-helper__scroll">
        <p className="about-panel__lede">
          Patch-bay for AI audio. A node-graph studio purpose-built for AI audio — patch models and
          operators, render with sample accuracy, and stay in the graph while you explore, compare, and
          share.
        </p>
        <p className="about-panel__body">
          General-purpose graph tools spread audio across scattered custom nodes. GroovyUI fills that gap
          with an audio-native registry, typed signal flow, provenance, and modular-synth ergonomics in
          one workflow.
        </p>
        <dl className="about-panel__meta">
          <div className="about-panel__meta-row">
            <dt>Rendering</dt>
            <dd>Sample-accurate offline · cached audition</dd>
          </div>
          <div className="about-panel__meta-row">
            <dt>Signals</dt>
            <dd>Audio, MIDI, stems, and control</dd>
          </div>
          <div className="about-panel__meta-row">
            <dt>License</dt>
            <dd>Apache 2.0 (core packages)</dd>
          </div>
          <div className="about-panel__meta-row">
            <dt>Developer</dt>
            <dd>
              <a
                className="about-panel__link"
                href={DEVELOPER_URL}
                target="_blank"
                rel="noopener noreferrer"
              >
                ONE Systemics
              </a>
            </dd>
          </div>
        </dl>
      </div>
    </aside>
  );
}
