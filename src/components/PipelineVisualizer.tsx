import React from "react";
import {
  CheckCircle2,
  Circle,
  Building2,
  MapPin,
  Heart,
  FileCheck,
  User,
  Compass,
  FileText,
  Upload,
  Camera,
  Layers,
  PhoneCall,
  Coins,
  PlaneTakeoff,
  Award,
  CheckSquare,
} from "lucide-react";
import { TargetStageMode } from "../types";

interface PipelineVisualizerProps {
  currentTargetMode: TargetStageMode;
  onSelectStage: (stage: TargetStageMode) => void;
  activeStageIndex: number;
  applicant?: any;
}

const PIPELINE_STAGES = [
  { id: "SELECT_VISA_TYPE", name: "1. Visa Type", icon: FileText, label: "Long-stay / Uniform" },
  { id: "DIPLOMATIC_MISSION", name: "2. Consular Post", icon: Building2, label: "Colombo Diplomatic Mission" },
  { id: "VISA_PURPOSE", name: "3. Purpose of Stay", icon: Compass, label: "Employment (D/AM)" },
  { id: "PARTICULAR_SITUATIONS", name: "4. Particulars", icon: Layers, label: "Family / Standard" },
  { id: "TERRITORIAL_JURISDICTION", name: "5. Jurisdiction", icon: MapPin, label: "National Visa" },
  { id: "DOCUMENTS_UPLOAD", name: "6. Supporting Docs", icon: Upload, label: "6 PDF Uploads & Declaration" },
  { id: "PERSONAL_DATA", name: "7. Personal Data", icon: User, label: "Applicant Bio (1/8)" },
  { id: "TRAVEL_DOCUMENT_OCCUPATION", name: "8. Passport & Job", icon: FileCheck, label: "Travel Document (2/8)" },
  { id: "APPLICANT_HOME_ADDRESS", name: "9. Home Address", icon: MapPin, label: "Sri Lanka / Colombo (3/8)" },
  { id: "HOST_DETAILS", name: "10. Host Details", icon: Building2, label: "RETEX GREEN Hotel (4/8)" },
  { id: "COMPANY_CONTACT", name: "11. Company Contact", icon: PhoneCall, label: "Work Permit & Contact (5/8)" },
  { id: "DETAILS_ABOUT_VISA", name: "12. Visa Requested", icon: Award, label: "Entries & Transport (6/8)" },
  { id: "COST_AND_MEANS", name: "13. Cost & Means", icon: Coins, label: "Support & Insurance (7/8)" },
  { id: "FAMILY_DETAILS", name: "14. Family & Spouse", icon: Heart, label: "Parents & Spouse (8/8)" },
  { id: "DETAILS_REGARDING_JOURNEY", name: "15. Journey Details", icon: PlaneTakeoff, label: "Dates & Border Post" },
  { id: "SUMMARY_FILE", name: "16. Summary File", icon: CheckSquare, label: "Final Review & Submit" },
];

export const PipelineVisualizer: React.FC<PipelineVisualizerProps> = ({
  currentTargetMode,
  onSelectStage,
  activeStageIndex,
  applicant,
}) => {
  const totalStages = PIPELINE_STAGES.length;

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 mb-6 shadow-xl backdrop-blur-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div className="flex items-center space-x-2">
          <div className="w-2 h-2 rounded-full bg-cyan-400 animate-ping"></div>
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-300">
            E-VISA Automated Sequence Pipeline ({totalStages} Stages)
          </h2>
        </div>
        <div className="flex items-center space-x-3 text-xs text-slate-400 font-mono">
          <span>
            Mode:{" "}
            <span className="text-cyan-400 font-bold">
              {currentTargetMode === "FULL_PIPELINE" ? "AUTOMATED FULL RUN" : currentTargetMode}
            </span>
          </span>
          <span className="text-slate-600">|</span>
          <span>
            Target Stage: <span className="text-emerald-400 font-bold">{activeStageIndex + 1}/{totalStages}</span>
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-9 gap-2">
        {PIPELINE_STAGES.map((stage, idx) => {
          const Icon = stage.icon;
          const isSelected = currentTargetMode === stage.id || (currentTargetMode === "FULL_PIPELINE" && idx === activeStageIndex);
          const isCompleted = currentTargetMode === "FULL_PIPELINE" ? idx < activeStageIndex : idx <= activeStageIndex;

          let displayLabel = stage.label;
          if (stage.id === "HOST_DETAILS" && applicant?.hostData?.hotel_name) {
            displayLabel = `${applicant.hostData.hotel_name} (4/8)`;
          }

          return (
            <button
              key={stage.id}
              onClick={() => onSelectStage(stage.id as TargetStageMode)}
              className={`flex flex-col text-left p-2.5 rounded-xl border transition-all text-xs relative group ${
                isSelected
                  ? "bg-gradient-to-br from-cyan-950/80 to-slate-900 border-cyan-500/80 text-cyan-200 shadow-lg shadow-cyan-950/50 ring-1 ring-cyan-500/40"
                  : isCompleted
                  ? "bg-slate-900/60 border-emerald-500/30 text-slate-300 hover:border-slate-700"
                  : "bg-slate-950/40 border-slate-800/80 text-slate-400 hover:border-slate-700 hover:text-slate-200"
              }`}
            >
              <div className="flex items-center justify-between w-full mb-1">
                <div className="p-1.5 rounded-lg bg-slate-800/80 text-cyan-400">
                  <Icon className="w-3.5 h-3.5" />
                </div>
                {isSelected ? (
                  <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
                ) : isCompleted ? (
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                ) : (
                  <Circle className="w-3.5 h-3.5 text-slate-600" />
                )}
              </div>
              <span className="font-semibold text-slate-200 truncate">{stage.name}</span>
              <span className="text-[10px] text-slate-400 truncate mt-0.5">{displayLabel}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
};
