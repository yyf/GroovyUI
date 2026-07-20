import type { Workflow } from "../types";
import { openAboutWindow } from "../aboutWindow";
import StudioSettingsMenu, { type StudioSettingsMenuProps } from "./StudioSettingsMenu";
import TemplateSelector from "./TemplateSelector";
import WorkflowGenerateButton from "./WorkflowGenerateButton";

import type { TemplateListItem } from "../api";

type Props = {
  templates: TemplateListItem[];
  selectedTemplateId: string;
  onSelectTemplate: (templateId: string) => void;
  onDeleteUserTemplate?: (templateId: string) => void | Promise<void>;
  onApplyWorkflow: (workflow: Workflow) => void;
  generateOpenNonce?: number;
  complianceWarnings: number;
  inferenceStubActive?: boolean;
  onModelBrowser: () => void;
  onCompliance: () => void;
  onShareWorkflow: () => void;
  workflowBarOpen: boolean;
  onToggleWorkflowBar: () => void;
  settings: Omit<
    StudioSettingsMenuProps,
    "onModelBrowser" | "onCompliance" | "complianceWarnings" | "workflowBarOpen" | "onToggleWorkflowBar"
  >;
};

export default function StudioTopBar({
  templates,
  selectedTemplateId,
  onSelectTemplate,
  onDeleteUserTemplate,
  onApplyWorkflow,
  generateOpenNonce = 0,
  complianceWarnings,
  inferenceStubActive = false,
  onModelBrowser,
  onCompliance,
  onShareWorkflow,
  workflowBarOpen,
  onToggleWorkflowBar,
  settings,
}: Props) {
  const open = workflowBarOpen;

  return (
    <header className={`top-bar${open ? " top-bar--open" : ""}`}>
      <button
        type="button"
        className="top-bar__brand"
        onClick={() => openAboutWindow()}
        title="About GroovyUI"
        aria-label="About GroovyUI"
      >
        GroovyUI
      </button>

      <div className={`top-bar__content${open ? "" : " top-bar__content--collapsed"}`}>
        <div className="top-bar__drawer">
          <TemplateSelector
            templates={templates}
            selectedId={selectedTemplateId}
            onSelect={onSelectTemplate}
            onDeleteUserTemplate={onDeleteUserTemplate}
          />
          <WorkflowGenerateButton onApply={onApplyWorkflow} openNonce={generateOpenNonce} />
        </div>
        <div className="top-bar__tools">
          {inferenceStubActive ? (
            <span
              className="top-bar__stub-pill"
              title="Stub inference is active — AI nodes use stand-ins, not real weights. Change in Settings → Inference."
            >
              Stub inference
            </span>
          ) : null}
          <button
            type="button"
            className="top-bar__tool"
            onClick={onModelBrowser}
            title="Model Browser (⌘K / Ctrl+K)"
            aria-keyshortcuts="Meta+K Control+K"
          >
            Models
            <kbd className="workflow-generate__kbd">⌘K</kbd>
          </button>
          <button
            type="button"
            className={`top-bar__tool${complianceWarnings > 0 ? " top-bar__tool--warn" : ""}`}
            onClick={onCompliance}
            title="License, provenance, authenticity, and disclosure"
          >
            Compliance{complianceWarnings > 0 ? ` (${complianceWarnings})` : ""}
          </button>
          <button
            type="button"
            className="top-bar__tool"
            onClick={onShareWorkflow}
            title="Download workflow as .groovy.json"
          >
            Share
          </button>
        </div>
      </div>

      <button
        type="button"
        className="top-bar__tab top-bar__tab--center"
        onClick={onToggleWorkflowBar}
        aria-expanded={open}
        title={open ? "Hide workflow bar" : "Show workflow bar"}
      >
        <span className="top-bar__tab-label">Workflow</span>
      </button>

      <StudioSettingsMenu
        {...settings}
        workflowBarOpen={workflowBarOpen}
        onToggleWorkflowBar={onToggleWorkflowBar}
      />
    </header>
  );
}
