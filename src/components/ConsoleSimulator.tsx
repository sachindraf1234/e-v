import React, { useRef, useEffect } from "react";
import { Terminal, Trash2, Play, RefreshCw, CheckCircle2, AlertTriangle, XCircle, Info, ShieldAlert } from "lucide-react";
import { AutomationLog, TargetStageMode } from "../types";

interface ConsoleSimulatorProps {
  logs: AutomationLog[];
  onClearLogs: () => void;
  onRunSimulation: () => void;
  isSimulating: boolean;
  targetMode: TargetStageMode;
}

export const ConsoleSimulator: React.FC<ConsoleSimulatorProps> = ({
  logs,
  onClearLogs,
  onRunSimulation,
  isSimulating,
  targetMode,
}) => {
  const terminalContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = terminalContainerRef.current;
    if (container) {
      const isAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 120;
      if (isAtBottom) {
        container.scrollTop = container.scrollHeight;
      }
    }
  }, [logs]);

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 pb-4 border-b border-slate-800">
        <div className="flex items-center space-x-3">
          <div className="p-3 bg-amber-500/10 text-amber-400 rounded-xl border border-amber-500/20">
            <Terminal className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-100 flex items-center space-x-2">
              <span>Chrome CDP Session Console & Pipeline Logs</span>
              <span className="bg-amber-500/20 text-amber-300 text-xs px-2 py-0.5 rounded-full font-mono font-semibold">
                Port 9222
              </span>
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Live automated execution terminal logging stdout output, session expiration checks, and DOM interaction events.
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={onClearLogs}
            className="inline-flex items-center space-x-1.5 px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-xl border border-slate-700 transition-colors"
          >
            <Trash2 className="w-4 h-4 text-slate-400" />
            <span>Clear Terminal</span>
          </button>

          <button
            onClick={onRunSimulation}
            disabled={isSimulating}
            className={`inline-flex items-center space-x-1.5 px-4 py-2 font-bold text-xs rounded-xl shadow-lg transition-all active:scale-95 ${
              isSimulating
                ? "bg-amber-600 text-amber-100 cursor-wait animate-pulse"
                : "bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white shadow-emerald-900/30"
            }`}
          >
            {isSimulating ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Simulating...</span>
              </>
            ) : (
              <>
                <Play className="w-4 h-4 fill-current" />
                <span>Execute CDP Simulation</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Terminal View */}
      <div className="bg-slate-950 rounded-xl border border-slate-800 font-mono text-xs overflow-hidden shadow-2xl">
        <div className="flex items-center justify-between px-4 py-2 bg-slate-900 border-b border-slate-800 text-slate-400">
          <div className="flex items-center space-x-2">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-500"></span>
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500"></span>
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
            <span className="ml-2 text-slate-300 font-semibold">
              stdout: selenium_remote_cdp_9222.log
            </span>
          </div>
          <span className="text-[10px] text-cyan-400 font-bold uppercase">
            Mode: {targetMode}
          </span>
        </div>

        <div ref={terminalContainerRef} className="p-4 max-h-[460px] overflow-y-auto space-y-2.5 leading-relaxed">
          {logs.length === 0 ? (
            <div className="text-center py-12 text-slate-600">
              <Terminal className="w-8 h-8 mx-auto mb-2 opacity-40" />
              <p>No CDP execution logs recorded yet.</p>
              <p className="text-[10px] text-slate-700 mt-1">
                Click "Execute CDP Simulation" above to run the automated workflow.
              </p>
            </div>
          ) : (
            logs.map((log) => {
              const isSuccess = log.status === "success";
              const isWarning = log.status === "warning";
              const isError = log.status === "error";

              return (
                <div
                  key={log.id}
                  className={`flex items-start space-x-2.5 p-2 rounded-lg border ${
                    isError
                      ? "bg-rose-950/30 border-rose-500/30 text-rose-300"
                      : isWarning
                      ? "bg-amber-950/20 border-amber-500/30 text-amber-300"
                      : isSuccess
                      ? "bg-emerald-950/20 border-emerald-500/30 text-emerald-300"
                      : "bg-slate-900/60 border-slate-800 text-slate-300"
                  }`}
                >
                  <div className="mt-0.5 shrink-0">
                    {isSuccess && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />}
                    {isWarning && <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />}
                    {isError && <XCircle className="w-3.5 h-3.5 text-rose-400" />}
                    {log.status === "info" && <Info className="w-3.5 h-3.5 text-cyan-400" />}
                  </div>

                  <div className="flex-1">
                    <div className="flex items-center space-x-2 text-[10px] text-slate-500">
                      <span>[{log.timestamp}]</span>
                      <span className="text-cyan-400 font-bold">[{log.stage}]</span>
                    </div>
                    <p className="mt-0.5 text-slate-200">{log.message}</p>
                    {log.xpath && (
                      <p className="mt-1 text-[10px] text-cyan-400/90 font-mono bg-slate-950/80 px-2 py-1 rounded border border-slate-800">
                        XPath: {log.xpath}
                      </p>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};
