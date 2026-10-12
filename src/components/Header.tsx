import React from "react";
import { Play, Code, Cpu, FileText, Settings, ShieldCheck, RefreshCw, Layers } from "lucide-react";
import { TargetStageMode } from "../types";

interface HeaderProps {
  activeTab: "schematics" | "extractor" | "documents" | "code" | "console" | "xpaths" | "agent";
  setActiveTab: (tab: "schematics" | "extractor" | "documents" | "code" | "console" | "xpaths" | "agent") => void;
  targetMode: TargetStageMode;
  setTargetMode: (mode: TargetStageMode) => void;
  fileNumber: string;
  onRunSimulation: () => void;
  isSimulating: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  setActiveTab,
  targetMode,
  setTargetMode,
  fileNumber,
  onRunSimulation,
  isSimulating,
}) => {
  return (
    <header className="bg-slate-900 border-b border-slate-800 text-slate-100 sticky top-0 z-50 shadow-xl">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo and App Title */}
          <div className="flex items-center space-x-3">
            <div className="bg-gradient-to-tr from-blue-600 to-cyan-500 p-2.5 rounded-xl shadow-lg shadow-blue-500/20">
              <Cpu className="w-6 h-6 text-white" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h1 className="text-lg font-bold bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">
                  E-VISA Automation Studio
                </h1>
                <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1.5 animate-pulse"></span>
                  CDP Active: 127.0.0.1:9222
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Romanian Ministry of Foreign Affairs Automation Engine | File:{" "}
                <span className="font-mono text-cyan-400 font-semibold">{fileNumber}</span>
              </p>
            </div>
          </div>

          {/* Target Mode Quick Selector */}
          <div className="hidden lg:flex items-center space-x-2 bg-slate-800/80 p-1.5 rounded-xl border border-slate-700/60">
            <Layers className="w-4 h-4 text-cyan-400 ml-2" />
            <span className="text-xs font-medium text-slate-300">Stage Entry:</span>
            <select
              value={targetMode}
              onChange={(e) => setTargetMode(e.target.value as TargetStageMode)}
              className="bg-slate-900 text-xs font-semibold text-cyan-300 border border-slate-700 rounded-lg px-2.5 py-1 focus:outline-none focus:ring-2 focus:ring-cyan-500 cursor-pointer"
            >
              <option value="FULL_PIPELINE">⚡ FULL PIPELINE (All Stages)</option>
              <option value="SELECT_VISA_TYPE">1. SELECT VISA TYPE & MISSION</option>
              <option value="DIPLOMATIC_MISSION">2. DIPLOMATIC MISSION POST</option>
              <option value="VISA_PURPOSE">3. PURPOSE OF STAY (D/AM)</option>
              <option value="PARTICULAR_SITUATIONS">4. PARTICULAR SITUATIONS</option>
              <option value="TERRITORIAL_JURISDICTION">5. TERRITORIAL JURISDICTION</option>
              <option value="PERSONAL_DATA">6. APPLICANT PERSONAL DATA</option>
              <option value="TRAVEL_DOCUMENT_OCCUPATION">7. PASSPORT & OCCUPATION</option>
              <option value="APPLICANT_HOME_ADDRESS">8. APPLICANT HOME ADDRESS</option>
              <option value="HOST_DETAILS">9. DETAILS REGARDING THE HOST</option>
              <option value="COMPANY_CONTACT">10. COMPANY CONTACT DETAILS</option>
              <option value="DETAILS_ABOUT_VISA">11. DETAILS ABOUT VISA REQUESTED</option>
              <option value="COST_AND_MEANS">12. COST & MEANS OF SUPPORT</option>
              <option value="FAMILY_DETAILS">13. APPLICANT FAMILY & SPOUSE</option>
              <option value="DETAILS_REGARDING_JOURNEY">14. DETAILS REGARDING JOURNEY</option>
              <option value="PHOTO_UPLOAD">15. BIOMETRIC PHOTO UPLOAD</option>
              <option value="DOCUMENTS_UPLOAD">16. SUPPORTING DOCUMENTS UPLOAD</option>
              <option value="SUMMARY_FILE">17. SUMMARY FILE REVIEW</option>
            </select>
          </div>

          {/* Action Trigger Buttons */}
          <div className="flex items-center space-x-3">
            <button
              onClick={onRunSimulation}
              disabled={isSimulating}
              className={`inline-flex items-center space-x-2 px-4 py-2 rounded-xl text-xs font-bold transition-all shadow-lg ${
                isSimulating
                  ? "bg-amber-600 text-amber-100 cursor-wait animate-pulse"
                  : "bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white shadow-emerald-900/30 active:scale-95"
              }`}
            >
              {isSimulating ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Executing Pipeline...</span>
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 fill-current" />
                  <span>Simulate CDP Pipeline</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex space-x-1 overflow-x-auto pb-2 pt-1 no-scrollbar border-t border-slate-800/80">
          <button
            onClick={() => setActiveTab("schematics")}
            className={`flex items-center space-x-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
              activeTab === "schematics"
                ? "bg-cyan-500/15 text-cyan-400 border border-cyan-500/30"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
            }`}
          >
            <Settings className="w-3.5 h-3.5" />
            <span>Master Schematics Data</span>
          </button>

          <button
            onClick={() => setActiveTab("extractor")}
            className={`flex items-center space-x-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
              activeTab === "extractor"
                ? "bg-cyan-500/15 text-cyan-400 border border-cyan-500/30"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
            }`}
          >
            <Cpu className="w-3.5 h-3.5 text-purple-400" />
            <span className="flex items-center space-x-1">
              <span>AI Extractor</span>
              <span className="bg-purple-500/20 text-purple-300 text-[10px] px-1.5 py-0.2 rounded font-mono">Gemini 3.6</span>
            </span>
          </button>

          <button
            onClick={() => setActiveTab("documents")}
            className={`flex items-center space-x-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
              activeTab === "documents"
                ? "bg-cyan-500/15 text-cyan-400 border border-cyan-500/30"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
            }`}
          >
            <FileText className="w-3.5 h-3.5 text-blue-400" />
            <span>Supporting Documents (6 Files)</span>
          </button>

          <button
            onClick={() => setActiveTab("code")}
            className={`flex items-center space-x-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
              activeTab === "code"
                ? "bg-cyan-500/15 text-cyan-400 border border-cyan-500/30"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
            }`}
          >
            <Code className="w-3.5 h-3.5 text-emerald-400" />
            <span>Python Selenium Code</span>
          </button>

          <button
            onClick={() => setActiveTab("agent")}
            className={`flex items-center space-x-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
              activeTab === "agent"
                ? "bg-cyan-500/20 text-cyan-300 border border-cyan-400/40 font-bold shadow-lg shadow-cyan-900/15"
                : "text-slate-300 hover:text-slate-100 hover:bg-slate-800/50"
            }`}
          >
            <Cpu className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />
            <span className="flex items-center space-x-1.5">
              <span>Real e-Visa Browser Agent</span>
              <span className="bg-cyan-500/10 text-cyan-300 text-[9px] px-1.5 py-0.2 rounded font-mono uppercase tracking-wider animate-pulse">LIVE SYNC</span>
            </span>
          </button>

          <button
            onClick={() => setActiveTab("console")}
            className={`flex items-center space-x-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
              activeTab === "console"
                ? "bg-cyan-500/15 text-cyan-400 border border-cyan-500/30"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
            }`}
          >
            <Play className="w-3.5 h-3.5 text-amber-400" />
            <span>Live CDP Console & Logs</span>
          </button>

          <button
            onClick={() => setActiveTab("xpaths")}
            className={`flex items-center space-x-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
              activeTab === "xpaths"
                ? "bg-cyan-500/15 text-cyan-400 border border-cyan-500/30"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
            }`}
          >
            <ShieldCheck className="w-3.5 h-3.5 text-rose-400" />
            <span>DOM Selectors & Session Guards</span>
          </button>
        </div>
      </div>
    </header>
  );
};
