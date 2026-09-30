import {
  TEMPLATE_LICENSE_MATRIX,
  templateLicenseSummary,
} from "../templateLicenseMatrix";

/** Template license matrix for the Inspector (studio dev mode / ⌘⇧D). */
export default function TemplateLicensePanel() {
  const summary = templateLicenseSummary();

  return (
    <aside
      className="node-helper node-helper--about node-helper--template-licenses"
      aria-label="Template licenses"
    >
      <header className="node-helper__header">
        <h2>Template licenses</h2>
        <span className="node-helper__id">{summary.total} templates</span>
      </header>
      <div className="node-helper__scroll">
        <p className="template-license-panel__counts">
          <span className="template-license-panel__pill template-license-panel__pill--safe">
            {summary.commercialSafe} commercial safe
          </span>
          {summary.caution > 0 ? (
            <span className="template-license-panel__pill template-license-panel__pill--caution">
              {summary.caution} caution
            </span>
          ) : null}
        </p>
        <table className="template-license-panel__matrix">
          <thead>
            <tr>
              <th>Template</th>
              <th>Model(s)</th>
              <th>Model license</th>
              <th>Final decision</th>
            </tr>
          </thead>
          <tbody>
            {TEMPLATE_LICENSE_MATRIX.map((row) => (
              <tr key={row.id} className={`template-license-panel__row--${row.tone}`}>
                <td>
                  <div className="template-license-panel__title">{row.title}</div>
                  <div className="template-license-panel__id">{row.id}</div>
                </td>
                <td>{row.models}</td>
                <td>{row.licenses}</td>
                <td className="template-license-panel__decision">{row.final}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="about-panel__body template-license-panel__foot">
          Commercial Safe = MIT / Apache-2.0 (or DSP-only).
        </p>
      </div>
    </aside>
  );
}
