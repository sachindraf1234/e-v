import React, { useEffect, useState, useRef } from "react";
import { Cpu, Download, RefreshCw, Terminal, Eye, CheckCircle2, AlertTriangle, AlertCircle, Play, HelpCircle, Activity, ExternalLink, Globe, PlayCircle, StopCircle, ArrowLeft, RotateCw, Keyboard, Send, Sparkles, Mail, FileText, Copy, Search, Check, X } from "lucide-react";
import { ApplicantRecord, AutomationConfig } from "../types";

interface RealTimeBrowserAgentProps {
  applicant: ApplicantRecord;
  config: AutomationConfig;
}

interface AgentLog {
  timestamp: string;
  stage: string;
  status: string;
  message: string;
}

interface AgentSession {
  status: string;
  currentStage: string;
  message: string;
  screenshot: string | null;
  timestamp: string | null;
  logs: AgentLog[];
}

export const RealTimeBrowserAgent: React.FC<RealTimeBrowserAgentProps> = ({ applicant, config }) => {
  // Mode Selection: "cloud" (runs inside Google AI Studio container sandbox) or "local" (python playwright sync)
  const [agentMode, setAgentMode] = useState<"cloud" | "local">("cloud");

  // LOCAL SYNC SESSION STATE
  const [localSession, setLocalSession] = useState<AgentSession>({
    status: "idle",
    currentStage: "Awaiting Connection",
    message: "Start the local Python browser agent to establish real-time visual synchronization.",
    screenshot: null,
    timestamp: null,
    logs: [
      {
        timestamp: new Date().toLocaleTimeString(),
        stage: "CONNECTIVITY",
        status: "info",
        message: "Local Browser Agent Monitor Initialized. Awaiting sync callbacks from your local Chrome window."
      }
    ]
  });

  // CLOUD SANDBOX AGENT STATE
  const [cloudStatus, setCloudStatus] = useState<string>("idle"); // "idle" | "running" | "loading" | "error"
  const [cloudScreenshot, setCloudScreenshot] = useState<string | null>(null);
  const [cloudUrl, setCloudUrl] = useState<string>("");
  const [cloudLogs, setCloudLogs] = useState<AgentLog[]>([
    {
      timestamp: new Date().toLocaleTimeString(),
      stage: "SYSTEM",
      status: "info",
      message: "Ready to launch server-side Chromium browser inside Google AI Studio container."
    }
  ]);

  // Interactive controls state
  const [inputText, setInputText] = useState<string>(" ");
  const [customUrl, setCustomUrl] = useState<string>("https://evisa.mae.ro/");
  const [isAutofilling, setIsAutofilling] = useState<boolean>(false);
  const [isInteracting, setIsInteracting] = useState<boolean>(false);
  const [isDownloading, setIsDownloading] = useState<boolean>(false);

  // Verification Link & Text Inspection state (persisted per applicant & global)
  const [verificationUrl, setVerificationUrl] = useState<string>(() => {
    try {
      return (
        applicant?.verificationLink ||
        (applicant?.id ? localStorage.getItem(`evisa_verify_link_${applicant.id}`) : null) ||
        localStorage.getItem("evisa_last_verification_link") ||
        ""
      );
    } catch (e) {
      return "";
    }
  });

  const handleVerificationUrlChange = (val: string) => {
    setVerificationUrl(val);
    try {
      localStorage.setItem("evisa_last_verification_link", val);
      if (applicant?.id) {
        localStorage.setItem(`evisa_verify_link_${applicant.id}`, val);
      }
    } catch (e) {}
  };

  useEffect(() => {
    if (applicant?.id) {
      const stored = localStorage.getItem(`evisa_verify_link_${applicant.id}`);
      if (stored && !verificationUrl) {
        setVerificationUrl(stored);
      }
    }
  }, [applicant?.id]);

  const [isInspectTextOpen, setIsInspectTextOpen] = useState<boolean>(false);
  const [inspectLoading, setInspectLoading] = useState<boolean>(false);
  const [extractedText, setExtractedText] = useState<string>("");
  const [extractedWords, setExtractedWords] = useState<string[]>([]);
  const [extractedFields, setExtractedFields] = useState<Array<{ name: string; value: string; type: string }>>([]);
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [copiedSuccess, setCopiedSuccess] = useState<string | null>(null);

  // Unified Automation Pipeline Progress State
  const [pipelineState, setPipelineState] = useState<{
    status: "idle" | "running" | "success" | "error";
    currentStep: number;
    totalSteps: number;
    message: string;
  }>({
    status: "idle",
    currentStep: 0,
    totalSteps: 7,
    message: "Ready to start from beginning or resume from last save point"
  });

  // Sync customUrl state with live cloudUrl updates
  useEffect(() => {
    if (cloudUrl) {
      setCustomUrl(cloudUrl);
    }
  }, [cloudUrl]);

  const logEndRef = useRef<HTMLDivElement>(null);
  const cloudLogEndRef = useRef<HTMLDivElement>(null);
  const cloudLogContainerRef = useRef<HTMLDivElement>(null);
  const localLogContainerRef = useRef<HTMLDivElement>(null);

  // Poll LOCAL agent sync status
  useEffect(() => {
    if (agentMode !== "local") return;

    const fetchStatus = async () => {
      try {
        const res = await fetch("/api/agent/status").catch(() => null);
        if (res && res.ok) {
          const contentType = res.headers.get("content-type");
          if (contentType && contentType.includes("application/json")) {
            const data = await res.json();
            if (data.success && data.session) {
              setLocalSession(data.session);
            }
          }
        }
      } catch (err) {
        // Silent catch for network jitter
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 1500);
    return () => clearInterval(interval);
  }, [agentMode]);

  // Poll CLOUD agent status
  useEffect(() => {
    if (agentMode !== "cloud") return;

    let consecutiveErrors = 0;
    const fetchCloudStatus = async () => {
      try {
        const res = await fetch("/api/cloud-agent/status").catch(() => null);
        if (res && res.ok) {
          consecutiveErrors = 0;
          const contentType = res.headers.get("content-type");
          if (contentType && contentType.includes("application/json")) {
            const data = await res.json();
            if (data.success) {
              setCloudStatus(data.status);
              setCloudUrl(data.url);
              if (data.screenshot) {
                setCloudScreenshot(data.screenshot);
              }
              if (data.logs) {
                setCloudLogs(data.logs);
              }
            }
          }
        } else {
          consecutiveErrors++;
          if (consecutiveErrors >= 5) {
            // Only flag error after multiple consecutive failures
            setCloudStatus("idle");
          }
        }
      } catch (err) {
        // Silent catch for network jitter
        consecutiveErrors++;
      }
    };

    fetchCloudStatus();
    const interval = setInterval(fetchCloudStatus, 1500);
    return () => clearInterval(interval);
  }, [agentMode]);

  // Autoscroll log containers only if user is already near bottom (never scroll outer window)
  useEffect(() => {
    const container = agentMode === "local" ? localLogContainerRef.current : cloudLogContainerRef.current;
    if (container) {
      const isAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 120;
      if (isAtBottom) {
        container.scrollTop = container.scrollHeight;
      }
    }
  }, [localSession.logs, cloudLogs, agentMode]);

  // LAUNCH CLOUD AGENT
  const handleLaunchCloudAgent = async () => {
    setCloudStatus("loading");
    setCloudLogs(prev => [
      ...prev,
      {
        timestamp: new Date().toLocaleTimeString(),
        stage: "SYSTEM",
        status: "info",
        message: "Triggering cloud agent initialization sequence..."
      }
    ]);

    try {
      const res = await fetch("/api/cloud-agent/launch", { method: "POST" });
      if (res.ok) {
        const contentType = res.headers.get("content-type");
        if (contentType && contentType.includes("application/json")) {
          const data = await res.json();
          if (data.success) {
            setCloudStatus("running");
            setCloudUrl(data.url);
          } else {
            setCloudStatus("error");
          }
        } else {
          setCloudStatus("error");
        }
      } else {
        setCloudStatus("error");
      }
    } catch (err: any) {
      console.error("Error launching cloud agent:", err);
      setCloudStatus("error");
    }
  };

  // SHUTDOWN CLOUD AGENT
  const handleStopCloudAgent = async () => {
    try {
      const res = await fetch("/api/cloud-agent/close", { method: "POST" });
      if (res.ok) {
        setCloudStatus("idle");
        setCloudScreenshot(null);
        setCloudUrl("");
      }
    } catch (err) {
      console.error("Error stopping cloud agent:", err);
    }
  };

  // INTERACT WITH CLOUD BROWSER (Clicks & Keystrokes)
  const interactWithCloudBrowser = async (action: string, payload: any): Promise<any> => {
    if (cloudStatus !== "running" || isInteracting) return null;
    setIsInteracting(true);

    try {
      const res = await fetch("/api/cloud-agent/interact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, ...payload })
      });

      if (res.ok) {
        const contentType = res.headers.get("content-type");
        if (contentType && contentType.includes("application/json")) {
          const data = await res.json();
          if (data.success) {
            setCloudUrl(data.url);
            setCloudScreenshot(data.screenshot);
            if (data.logs) {
              setCloudLogs(data.logs);
            }
            return data;
          }
          return data;
        }
      }
      return null;
    } catch (err) {
      console.error("Error interacting with cloud browser:", err);
      return null;
    } finally {
      setIsInteracting(false);
    }
  };

  // CAPTURE MOUSE CLICK ON LIVE CLOUD SCREENSHOT
  const handleScreenshotClick = async (e: React.MouseEvent<HTMLImageElement>) => {
    const img = e.currentTarget;
    const rect = img.getBoundingClientRect();
    
    // Calculate percentage coords to scale seamlessly matching 1280x800 page viewport
    const xPercent = (e.clientX - rect.left) / rect.width;
    const yPercent = (e.clientY - rect.top) / rect.height;
    
    const x = xPercent * 1280;
    const y = yPercent * 800;

    await interactWithCloudBrowser("click", { x, y });
  };

  // CAPTURE MOUSE WHEEL SCROLL ON LIVE CLOUD SCREENSHOT
  const handleScreenshotWheel = async (e: React.WheelEvent<HTMLDivElement>) => {
    // Scroll cloud viewport without scrolling the main application window
    e.preventDefault();
    const deltaY = e.deltaY > 0 ? 300 : -300;
    await interactWithCloudBrowser("scroll", { deltaY });
  };

  // EXECUTE TEXT TYPING
  const handleSendType = async () => {
    if (!inputText.trim()) return;
    await interactWithCloudBrowser("type", { text: inputText });
    setInputText("");
  };

  // REMOTE ADDRESS BAR CUSTOM NAVIGATION
  const handleNavigateToCustomUrl = async () => {
    if (!customUrl.trim() || cloudStatus !== "running") return;
    let url = customUrl.trim();
    if (!/^https?:\/\//i.test(url)) {
      url = "https://" + url;
    }
    await interactWithCloudBrowser("navigate", { url });
  };

  // NAVIGATE TO PASTED VERIFICATION LINK
  const handleVerifyLinkInSandbox = async () => {
    if (!verificationUrl.trim() || cloudStatus !== "running") return;
    let url = verificationUrl.trim();
    if (!/^https?:\/\//i.test(url)) {
      url = "https://" + url;
    }
    handleVerificationUrlChange(url);
    await interactWithCloudBrowser("navigate", { url });
  };

  // AUTOMATED PIPELINE: RUN FULL END-TO-END PIPELINE (STEPS 1 TO 11: ALL PAGES UP TO TYPE OF HOST)
  const handleRunFullPipeline = async () => {
    if (cloudStatus !== "running" || isAutofilling) return;
    setIsAutofilling(true);
    setPipelineState({
      status: "running",
      currentStep: 1,
      totalSteps: 11,
      message: "🚀 Starting / Resuming Automation Pipeline (Step-by-Step Live Execution)..."
    });

    try {
      let stepCount = 0;
      const maxSteps = 15;
      let isDone = false;
      let lastStage = "";

      while (stepCount < maxSteps && !isDone) {
        stepCount++;
        setPipelineState({
          status: "running",
          currentStep: Math.min(stepCount, 11),
          totalSteps: 11,
          message: `⚡ Executing Step ${Math.min(stepCount, 11)}/11: ${lastStage ? `Current Stage: ${lastStage}` : "Detecting stage & autofilling..."}`
        });

        const res = await fetch("/api/cloud-agent/pipeline-step", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ 
            applicant,
            verificationUrl: verificationUrl.trim()
          })
        });

        const contentType = res.headers.get("content-type");
        if (!contentType || !contentType.includes("application/json")) {
          const text = await res.text();
          throw new Error(res.ok ? "Server returned non-JSON response" : `Server error (${res.status}): ${text.slice(0, 100)}`);
        }

        const data = await res.json();

        if (data.url) setCloudUrl(data.url);
        if (data.screenshot) setCloudScreenshot(data.screenshot);
        if (data.logs) setCloudLogs(data.logs);

        if (!data.success) {
          throw new Error(data.error || `Error at stage ${data.stageBefore || "unknown"}`);
        }

        lastStage = data.currentStage;

        if (data.isComplete || data.currentStage === "SUMMARY_PAGE") {
          isDone = true;
          setPipelineState({
            status: "success",
            currentStep: 11,
            totalSteps: 11,
            message: `🎉 Automation pipeline executed successfully! Completed on stage (${data.currentStage}).`
          });
          break;
        }

        if (data.stageBefore === data.currentStage && stepCount >= 3) {
          setPipelineState({
            status: "success",
            currentStep: Math.min(stepCount, 11),
            totalSteps: 11,
            message: `ℹ️ Step executed for ${data.currentStage}. State synchronized.`
          });
          break;
        }

        // Brief delay for smooth UI update
        await new Promise((r) => setTimeout(r, 600));
      }
    } catch (err: any) {
      console.error("Error executing automation pipeline:", err);
      setPipelineState({
        status: "error",
        currentStep: 0,
        totalSteps: 11,
        message: err.message || "Failed to execute pipeline."
      });
    } finally {
      setIsAutofilling(false);
    }
  };

  // AUTOMATED PIPELINE: RUN COMPLETE PIPELINE FROM SINGLE BUTTON
  const handleStartAutomationPipeline = async () => {
    if (cloudStatus !== "running") return;
    await handleRunFullPipeline();
  };

  // EXTRACT VISIBLE PAGE TEXT FOR WORD SELECTION & COPYING
  const handleFetchPageText = async () => {
    if (cloudStatus !== "running") return;
    setIsInspectTextOpen(true);
    setInspectLoading(true);
    try {
      const res = await fetch("/api/cloud-agent/page-text");
      if (res.ok && res.headers.get("content-type")?.includes("application/json")) {
        const data = await res.json();
        if (data.success) {
          setExtractedText(data.fullText || "");
          setExtractedWords(data.words || []);
          setExtractedFields(data.formFields || []);
        }
      }
    } catch (err) {
      console.error("Error fetching page text:", err);
    } finally {
      setInspectLoading(false);
    }
  };

  // COPY TEXT HELPER
  const copyToClipboard = (txt: string, label: string = "Text") => {
    navigator.clipboard.writeText(txt);
    setCopiedSuccess(`${label} copied to clipboard!`);
    setTimeout(() => setCopiedSuccess(null), 2500);
  };

  // TRIGGER CLOUD FORM AUTO-FILL
  const handleTriggerCloudAutofill = async () => {
    if (cloudStatus !== "running" || isAutofilling) return;
    setIsAutofilling(true);

    try {
      const res = await fetch("/api/cloud-agent/autofill", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          applicant,
          section: "all"
        })
      });

      if (res.ok && res.headers.get("content-type")?.includes("application/json")) {
        const data = await res.json();
        if (data.success) {
          setCloudUrl(data.url);
          setCloudScreenshot(data.screenshot);
          if (data.logs) {
            setCloudLogs(data.logs);
          }
        }
      }
    } catch (err) {
      console.error("Error triggering cloud autofill:", err);
    } finally {
      setIsAutofilling(false);
    }
  };

  const handleResetSession = async () => {
    try {
      const res = await fetch("/api/agent/reset", { method: "POST" });
      if (res.ok && res.headers.get("content-type")?.includes("application/json")) {
        const data = await res.json();
        if (data.success) {
          setLocalSession(data.session);
        }
      }
    } catch (err) {
      console.error("Error resetting local agent session:", err);
    }
  };

  const handleDownloadAgent = async () => {
    setIsDownloading(true);
    try {
      const serverUrl = window.location.origin;
      const res = await fetch("/api/generate-python-script", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ applicant, config: { ...config, serverUrl } })
      });

      if (res.ok && res.headers.get("content-type")?.includes("application/json")) {
        const data = await res.json();
        if (data.success && data.script) {
          const blob = new Blob([data.script], { type: "text/plain" });
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `run_evisa_automation_live_sync.py`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          window.URL.revokeObjectURL(url);
        }
      }
    } catch (err) {
      console.error("Error downloading Python agent script:", err);
    } finally {
      setIsDownloading(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "running":
        return (
          <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 animate-pulse">
            <span className="w-2 h-2 rounded-full bg-emerald-400 mr-2 animate-ping"></span>
            ACTIVE BROWSER ONLINE
          </span>
        );
      case "loading":
        return (
          <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-amber-500/10 text-amber-400 border border-amber-500/30 animate-pulse">
            <span className="w-2 h-2 rounded-full bg-amber-400 mr-2"></span>
            STARTING AGENT CONTAINER...
          </span>
        );
      case "paused":
        return (
          <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-amber-500/15 text-amber-400 border border-amber-500/30">
            <span className="w-2 h-2 rounded-full bg-amber-400 mr-2"></span>
            INTERACTION REQUIRED
          </span>
        );
      case "success":
        return (
          <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-blue-500/15 text-blue-400 border border-blue-500/30">
            <CheckCircle2 className="w-3.5 h-3.5 mr-1.5 text-blue-400" />
            COMPLETED SUCCESSFULLY
          </span>
        );
      case "error":
        return (
          <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-rose-500/15 text-rose-400 border border-rose-500/30">
            <AlertTriangle className="w-3.5 h-3.5 mr-1.5 text-rose-400" />
            EXCEPTION FLAGGED
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-slate-800 text-slate-400 border border-slate-700">
            <Activity className="w-3.5 h-3.5 mr-1.5 text-slate-500" />
            AGENT IDLE
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      
      {/* Tab Switcher: Cloud (Sandbox) vs Local Mode */}
      <div className="bg-slate-900/60 border border-slate-800 p-1.5 rounded-2xl flex items-center justify-between shadow-lg">
        <div className="flex items-center space-x-1.5 w-full md:w-auto">
          <button
            onClick={() => setAgentMode("cloud")}
            className={`flex-1 md:flex-none flex items-center justify-center space-x-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              agentMode === "cloud"
                ? "bg-cyan-500/20 text-cyan-300 border border-cyan-400/40 shadow-lg"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Cpu className="w-4 h-4 text-cyan-400" />
            <span>Cloud Agent Sandbox (Inside Google AI Studio)</span>
          </button>

          <button
            onClick={() => setAgentMode("local")}
            className={`flex-1 md:flex-none flex items-center justify-center space-x-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              agentMode === "local"
                ? "bg-cyan-500/20 text-cyan-300 border border-cyan-400/40 shadow-lg"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Terminal className="w-4 h-4 text-emerald-400" />
            <span>Local Browser Agent (Run on your PC)</span>
          </button>
        </div>

        <span className="hidden md:inline-flex items-center space-x-1.5 bg-slate-950 px-3 py-1.5 rounded-lg border border-slate-800 text-[11px] text-slate-400 font-mono">
          <Activity className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />
          <span>Active Pipeline Controller</span>
        </span>
      </div>

      {/* CLOUD SANDBOX AGENT INTERACTION PANEL */}
      {agentMode === "cloud" && (
        <div className="space-y-6">
          {/* Top Banner Cloud Controls */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center space-x-4">
              <div className="p-3 bg-cyan-500/10 rounded-xl border border-cyan-500/20 text-cyan-400">
                <Cpu className="w-6 h-6 animate-pulse" />
              </div>
              <div>
                <div className="flex items-center space-x-3">
                  <h2 className="text-lg font-bold text-slate-100">AI Cloud Browser Agent (Server-Side)</h2>
                  {getStatusBadge(cloudStatus)}
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  Runs directly on the Google AI Studio cloud sandbox. No local Python script, Chromium driver, or local setup required!
                </p>
              </div>
            </div>

            <div className="flex items-center space-x-3 w-full md:w-auto">
              {cloudStatus === "running" ? (
                <>
                  <button
                    onClick={handleTriggerCloudAutofill}
                    disabled={isAutofilling}
                    className="flex-1 md:flex-none inline-flex items-center justify-center space-x-2 px-5 py-2.5 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white rounded-xl text-xs font-bold transition-all shadow-lg active:scale-95 cursor-pointer disabled:opacity-50"
                  >
                    {isAutofilling ? (
                      <RefreshCw className="w-4 h-4 animate-spin" />
                    ) : (
                      <Sparkles className="w-4 h-4" />
                    )}
                    <span>AI Auto-Fill Current Form</span>
                  </button>

                  <button
                    onClick={handleStopCloudAgent}
                    className="flex-1 md:flex-none inline-flex items-center justify-center space-x-2 px-4 py-2.5 bg-rose-500/20 hover:bg-rose-500/30 border border-rose-500/40 rounded-xl text-xs font-bold text-rose-300 transition-all cursor-pointer"
                  >
                    <StopCircle className="w-4 h-4 text-rose-400" />
                    <span>Stop Browser</span>
                  </button>
                </>
              ) : (
                <button
                  onClick={handleLaunchCloudAgent}
                  disabled={cloudStatus === "loading"}
                  className="w-full md:w-auto inline-flex items-center justify-center space-x-2.5 px-6 py-3 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white rounded-xl text-xs font-extrabold transition-all shadow-lg shadow-cyan-900/35 active:scale-95 cursor-pointer disabled:opacity-50"
                >
                  {cloudStatus === "loading" ? (
                    <RefreshCw className="w-4.5 h-4.5 animate-spin" />
                  ) : (
                    <PlayCircle className="w-4.5 h-4.5 text-white" />
                  )}
                  <span>Launch Cloud Browser Sandbox</span>
                </button>
              )}
            </div>
          </div>

          {/* E-Visa Full Automation Control & Verification Console */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 sm:p-5 space-y-4 shadow-xl">
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
              <div className="flex items-center space-x-3">
                <div className="w-11 h-11 rounded-xl bg-gradient-to-br from-emerald-500/20 to-cyan-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400 font-bold shadow-md">
                  <Play className="w-5 h-5 fill-emerald-400 text-emerald-400" />
                </div>
                <div>
                  <h4 className="text-sm font-bold text-slate-100 flex flex-wrap items-center gap-2">
                    <span>E-Visa Automation Control Center</span>
                    <span className="text-xs px-2.5 py-0.5 rounded-md bg-emerald-500/15 text-emerald-400 border border-emerald-500/20 font-mono font-semibold">
                      transarabianofficial@gmail.com
                    </span>
                  </h4>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Dynamic Automation: Starts from Step 1 or automatically resumes directly from your saved step (Summary ➔ Visa Type ➔ Diplomatic Mission ➔ Purpose: Employment marked D/AM, Save & Next).
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {/* Single Master Button: Run All Steps */}
                <button
                  onClick={handleStartAutomationPipeline}
                  disabled={cloudStatus !== "running" || isInteracting || isAutofilling}
                  className="px-6 py-2.5 bg-gradient-to-r from-emerald-600 via-teal-600 to-cyan-600 hover:from-emerald-500 hover:to-cyan-500 text-white font-extrabold text-xs sm:text-sm rounded-xl shadow-xl hover:shadow-emerald-500/25 transition-all flex items-center space-x-2.5 cursor-pointer disabled:opacity-50 active:scale-95 border border-emerald-400/30"
                  title="Starts from beginning or resumes automatically from current saved step"
                >
                  {isAutofilling ? (
                    <RefreshCw className="w-4 h-4 animate-spin" />
                  ) : (
                    <Play className="w-4 h-4 fill-white" />
                  )}
                  <span>🚀 Run All Steps</span>
                </button>
              </div>
            </div>

            {/* Live Progress & Status Display */}
            {pipelineState.status !== "idle" && (
              <div className={`p-4 rounded-xl border transition-all flex items-center justify-between gap-4 ${
                pipelineState.status === "running"
                  ? "bg-amber-950/25 border-amber-500/40 text-amber-200"
                  : pipelineState.status === "success"
                  ? "bg-emerald-950/25 border-emerald-500/40 text-emerald-200"
                  : "bg-rose-950/25 border-rose-500/40 text-rose-200"
              }`}>
                <div className="flex items-center space-x-3">
                  {pipelineState.status === "running" ? (
                    <div className="w-8 h-8 rounded-lg bg-amber-500/20 border border-amber-500/40 flex items-center justify-center shrink-0">
                      <RefreshCw className="w-4 h-4 animate-spin text-amber-400" />
                    </div>
                  ) : pipelineState.status === "success" ? (
                    <div className="w-8 h-8 rounded-lg bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center shrink-0">
                      <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    </div>
                  ) : (
                    <div className="w-8 h-8 rounded-lg bg-rose-500/20 border border-rose-500/40 flex items-center justify-center shrink-0">
                      <AlertCircle className="w-4 h-4 text-rose-400" />
                    </div>
                  )}
                  <div>
                    <div className="text-xs font-bold font-mono tracking-wide uppercase flex items-center gap-2">
                      <span>
                        {pipelineState.status === "running"
                          ? `Executing Step ${pipelineState.currentStep} of ${pipelineState.totalSteps}`
                          : pipelineState.status === "success"
                          ? "Automation Complete"
                          : "Automation Notice"}
                      </span>
                    </div>
                    <p className="text-xs mt-0.5 opacity-90">
                      {pipelineState.message}
                    </p>
                  </div>
                </div>

                {pipelineState.status === "running" && (
                  <div className="hidden sm:flex items-center space-x-1.5 font-mono text-[11px] text-amber-300/80 bg-amber-950/50 px-3 py-1.5 rounded-lg border border-amber-500/20">
                    <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping"></span>
                    <span>Live Cloud Processing</span>
                  </div>
                )}
              </div>
            )}

            {/* Direct Verification Link Input */}
            <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-center pt-1 border-t border-slate-800/80">
              <div className="md:col-span-8 flex items-center space-x-2">
                <div className="relative flex-1">
                  <input
                    type="text"
                    value={verificationUrl}
                    onChange={(e) => handleVerificationUrlChange(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleVerifyLinkInSandbox();
                    }}
                    placeholder="Paste E-Visa verification link from transarabianofficial@gmail.com (e.g. https://evisa.mae.ro/...)"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-2.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500 font-mono shadow-inner"
                  />
                  {verificationUrl && (
                    <button
                      onClick={() => handleVerificationUrlChange("")}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 text-xs font-bold"
                    >
                      ×
                    </button>
                  )}
                </div>
                <button
                  onClick={handleVerifyLinkInSandbox}
                  disabled={!verificationUrl.trim() || cloudStatus !== "running" || isInteracting}
                  className="px-4 py-2.5 bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-xs rounded-xl transition-all flex items-center space-x-1.5 shrink-0 cursor-pointer disabled:opacity-50 shadow-md"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  <span>Verify Link in Sandbox</span>
                </button>
              </div>

              <div className="md:col-span-4 flex items-center justify-end space-x-2 text-[11px] text-slate-400 font-mono">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
                <span>Direct Cloud Navigation Active</span>
              </div>
            </div>
          </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            
            {/* Left Column: Interactive Visual Cloud Screen Viewport */}
            <div className="lg:col-span-8 flex flex-col space-y-4">
              <div className="bg-slate-900 border border-slate-800 rounded-2xl flex flex-col flex-1 overflow-hidden shadow-2xl">
                
                {/* Browser Address and Interactive Toolbar */}
                <div className="bg-slate-950 px-4 py-3 border-b border-slate-800 flex flex-col sm:flex-row items-center gap-3 justify-between">
                  
                  {/* Browser Window Window buttons */}
                  <div className="flex items-center justify-between w-full sm:w-auto">
                    <div className="flex items-center space-x-2">
                      <span className="w-3 h-3 rounded-full bg-rose-500"></span>
                      <span className="w-3 h-3 rounded-full bg-amber-500"></span>
                      <span className="w-3 h-3 rounded-full bg-emerald-500"></span>
                    </div>

                    <div className="sm:hidden text-[10px] font-mono text-slate-500 bg-slate-900 px-2 py-0.5 rounded border border-slate-800">
                      CLOUD FEED
                    </div>
                  </div>

                  {/* Browser Controls */}
                  <div className="flex items-center space-x-2 w-full sm:w-auto">
                    <button
                      onClick={() => interactWithCloudBrowser("back", {})}
                      disabled={cloudStatus !== "running"}
                      className="p-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-lg text-slate-400 hover:text-slate-200 disabled:opacity-30 cursor-pointer"
                      title="Back"
                    >
                      <ArrowLeft className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => interactWithCloudBrowser("reload", {})}
                      disabled={cloudStatus !== "running"}
                      className="p-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-lg text-slate-400 hover:text-slate-200 disabled:opacity-30 cursor-pointer"
                      title="Reload"
                    >
                      <RotateCw className="w-3.5 h-3.5" />
                    </button>

                    <div className="flex-1 sm:flex-none flex items-center bg-slate-900 px-2.5 py-1 rounded-xl border border-slate-800 sm:w-80 justify-center">
                      <Globe className="w-3.5 h-3.5 text-cyan-400 mr-2 flex-shrink-0" />
                      <input
                        type="text"
                        value={customUrl}
                        onChange={(e) => setCustomUrl(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleNavigateToCustomUrl();
                        }}
                        disabled={cloudStatus !== "running"}
                        className="w-full bg-transparent text-xs font-mono text-slate-200 placeholder-slate-600 focus:outline-none disabled:opacity-50"
                        placeholder="Paste eVisa URL and press Enter..."
                      />
                      {cloudStatus === "running" && (
                        <button
                          onClick={handleNavigateToCustomUrl}
                          className="ml-1.5 px-2 py-0.5 bg-cyan-600 hover:bg-cyan-500 text-white rounded text-[10px] font-bold transition-all shrink-0 cursor-pointer"
                        >
                          GO
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Active Connection Tag & Official Account Badge */}
                  <div className="hidden sm:flex items-center space-x-2 text-xs text-slate-500">
                    <span className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[10px] px-2.5 py-1 rounded-lg font-bold flex items-center space-x-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                      <span>Account: transarabianofficial@gmail.com</span>
                    </span>
                    <span className="bg-cyan-500/10 text-cyan-400 text-[10px] px-2 py-1 rounded font-bold uppercase tracking-wider">
                      INTERACTIVE SANDBOX
                    </span>
                  </div>
                </div>

                {/* Cloud Canvas Screenshot Viewport with Mouse Wheel listener */}
                <div 
                  onWheel={handleScreenshotWheel}
                  className="relative flex-1 bg-slate-950 min-h-[480px] max-h-[680px] overflow-auto flex flex-col items-center justify-center p-3 select-none"
                >
                  {cloudStatus === "running" && cloudScreenshot ? (
                    <div className="relative rounded-lg overflow-hidden border border-slate-800/80 shadow-2xl max-w-full">
                      {/* Top Viewport Navigation Quick Action Toolbar */}
                      <div className="bg-slate-900/90 backdrop-blur-md px-3 py-2 border-b border-slate-800 flex flex-wrap items-center justify-between gap-2 text-xs">
                        <div className="flex items-center space-x-1.5">
                          <span className="text-[10px] font-mono font-semibold text-slate-400 mr-1">SCROLL:</span>
                          <button
                            onClick={() => interactWithCloudBrowser("scroll", { deltaY: -350 })}
                            disabled={isInteracting}
                            className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-md text-[11px] font-medium transition-all active:scale-95 cursor-pointer disabled:opacity-50"
                          >
                            ↑ Scroll Up
                          </button>
                          <button
                            onClick={() => interactWithCloudBrowser("scroll", { deltaY: 350 })}
                            disabled={isInteracting}
                            className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-md text-[11px] font-medium transition-all active:scale-95 cursor-pointer disabled:opacity-50"
                          >
                            ↓ Scroll Down
                          </button>
                          <button
                            onClick={() => interactWithCloudBrowser("scroll", { deltaY: -9999 })}
                            disabled={isInteracting}
                            className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 rounded-md text-[10px] font-mono cursor-pointer"
                          >
                            Top
                          </button>
                        </div>

                        <div className="flex items-center space-x-1.5 flex-wrap gap-y-1">
                          <button
                            onClick={handleFetchPageText}
                            className="px-2.5 py-1 bg-purple-600/80 hover:bg-purple-500 text-white rounded-md text-[11px] font-bold transition-all flex items-center space-x-1 cursor-pointer"
                            title="Extract and copy words directly from sandbox"
                          >
                            <FileText className="w-3 h-3" />
                            <span>📝 Inspect Words</span>
                          </button>

                          <button
                            onClick={() => interactWithCloudBrowser("back", {})}
                            disabled={isInteracting}
                            className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 rounded-md text-[11px] cursor-pointer disabled:opacity-50"
                          >
                            Back
                          </button>
                        </div>
                      </div>

                      <img
                        src={cloudScreenshot}
                        alt="E-Visa Romania Portal Screenshot"
                        className="object-contain max-h-[600px] w-full cursor-default active:scale-99 transition-all"
                        onClick={handleScreenshotClick}
                        referrerPolicy="no-referrer"
                      />

                      {/* Interaction HUD Overlay */}
                      {isInteracting && (
                        <div className="absolute inset-0 bg-slate-950/45 backdrop-blur-[1px] flex items-center justify-center z-10">
                          <div className="bg-slate-900/90 border border-cyan-500/30 px-4 py-2.5 rounded-xl shadow-xl flex items-center space-x-3 text-cyan-300 text-xs font-bold font-mono">
                            <RefreshCw className="w-4 h-4 animate-spin text-cyan-400" />
                            <span>TRANSMITTING ACTION TO CLOUD CONTAINER...</span>
                          </div>
                        </div>
                      )}

                      {/* Info floating tag */}
                      <div className="absolute bottom-4 left-4 bg-slate-950/85 backdrop-blur-md px-3 py-1.5 rounded-lg border border-slate-800/80 flex items-center space-x-2 text-[10px] text-slate-300 font-mono">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
                        <span>Mouse wheel or Scroll buttons above to move up/down. Click directly to interact!</span>
                      </div>
                    </div>
                  ) : cloudStatus === "loading" ? (
                    <div className="text-center max-w-sm p-6 space-y-4">
                      <div className="mx-auto w-14 h-14 rounded-full bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400 animate-spin">
                        <RefreshCw className="w-7 h-7 text-cyan-400" />
                      </div>
                      <div>
                        <h3 className="text-sm font-bold text-slate-200">Spawning Sandbox Browser Instance...</h3>
                        <p className="text-[11px] text-slate-400 mt-2 leading-relaxed">
                          Installing and initializing headless Puppeteer-core and Chromium driver layers inside the server-side container to direct-connect...
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div className="text-center max-w-md p-8 space-y-6">
                      <div className="mx-auto w-16 h-16 rounded-full bg-slate-900 border border-slate-800 flex items-center justify-center text-slate-400">
                        <Cpu className="w-8 h-8 text-cyan-400 animate-pulse" />
                      </div>
                      <div>
                        <h3 className="text-sm font-bold text-slate-200">Cloud Browser Sandbox Offline</h3>
                        <p className="text-xs text-slate-400 mt-2 leading-relaxed">
                          Launch the integrated, server-side E-Visa Browser Agent to securely view and fill forms directly inside Google AI Studio container sandbox!
                        </p>
                      </div>

                      {/* Prominent Launch Button in Viewport */}
                      <button
                        onClick={handleLaunchCloudAgent}
                        disabled={cloudStatus === "loading"}
                        className="w-full inline-flex items-center justify-center space-x-2.5 px-6 py-4 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white rounded-xl text-xs font-extrabold transition-all shadow-xl shadow-cyan-900/35 active:scale-95 cursor-pointer disabled:opacity-50"
                      >
                        {cloudStatus === "loading" ? (
                          <RefreshCw className="w-4.5 h-4.5 animate-spin" />
                        ) : (
                          <PlayCircle className="w-4.5 h-4.5 text-white animate-pulse" />
                        )}
                        <span>Launch Cloud Browser Sandbox Now</span>
                      </button>

                      <div className="bg-slate-900/50 border border-slate-800/60 rounded-xl p-4 text-left space-y-3">
                        <h4 className="text-xs font-bold text-cyan-400 uppercase tracking-wider flex items-center space-x-1.5">
                          <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                          <span>No Key Needed & Complete Isolation</span>
                        </h4>
                        <ol className="list-decimal list-inside text-[11px] text-slate-300 space-y-2 leading-relaxed">
                          <li>
                            Click the <span className="text-cyan-300 font-semibold">"Launch Cloud Browser Sandbox Now"</span> button above to startup server browser.
                          </li>
                          <li>
                            It will automatically direct-connect to the Romanian E-Visa Portal inside our server and load the Draft/Login page.
                          </li>
                          <li>
                            Solve any Romanian eVisa CAPTCHAs by clicking directly on the live interactive screen.
                          </li>
                          <li>
                            Click <span className="text-emerald-300 font-semibold">"AI Auto-Fill Current Form"</span> to execute state-aware automation mapping and let Gemini Vision check for errors!
                          </li>
                        </ol>
                      </div>
                    </div>
                  )}
                </div>

                {/* Keyboard Keystroke Typings Hud */}
                {cloudStatus === "running" && (
                  <div className="bg-slate-950 p-4 border-t border-slate-800 flex flex-col sm:flex-row gap-3 items-center">
                    <div className="flex items-center space-x-2 text-slate-400 text-xs w-full sm:w-auto flex-shrink-0">
                      <Keyboard className="w-4 h-4 text-cyan-400" />
                      <span>Remote Input:</span>
                    </div>

                    <div className="flex items-center space-x-2 w-full">
                      <input
                        type="text"
                        value={inputText}
                        onChange={(e) => setInputText(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleSendType();
                        }}
                        placeholder="Click an input field above, then type text here and click Send..."
                        className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
                        disabled={isInteracting}
                      />
                      <button
                        onClick={handleSendType}
                        disabled={isInteracting || !inputText.trim()}
                        className="px-3.5 py-1.5 bg-cyan-600 hover:bg-cyan-500 rounded-lg text-xs font-bold text-white transition-all flex items-center space-x-1.5 cursor-pointer disabled:opacity-50"
                      >
                        <Send className="w-3 h-3 text-white" />
                        <span>Send</span>
                      </button>
                    </div>

                    <div className="flex items-center space-x-1.5 w-full sm:w-auto justify-end">
                      <button
                        onClick={() => interactWithCloudBrowser("key", { key: "Tab" })}
                        className="px-2 py-1 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded text-[10px] font-mono text-slate-300 cursor-pointer"
                      >
                        TAB
                      </button>
                      <button
                        onClick={() => interactWithCloudBrowser("key", { key: "Enter" })}
                        className="px-2 py-1 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded text-[10px] font-mono text-slate-300 cursor-pointer"
                      >
                        ENTER
                      </button>
                      <button
                        onClick={() => interactWithCloudBrowser("key", { key: "Backspace" })}
                        className="px-2 py-1 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded text-[10px] font-mono text-slate-300 cursor-pointer"
                      >
                        BKSP
                      </button>
                    </div>
                  </div>
                )}

              </div>
            </div>

            {/* Right Column: Server Cloud Agent Console Log and Output */}
            <div className="lg:col-span-4 flex flex-col space-y-4">
              
              {/* Target Applicant Details card */}
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-xl space-y-3">
                <h3 className="text-xs font-bold text-cyan-400 uppercase tracking-wider flex items-center space-x-1.5">
                  <Activity className="w-4 h-4 text-cyan-400 animate-pulse" />
                  <span>Applicant Form Data Source</span>
                </h3>
                
                <div className="space-y-2 bg-slate-950 p-3 rounded-xl border border-slate-800/80 text-[11px] font-mono">
                  <div className="flex justify-between border-b border-slate-900 pb-1.5">
                    <span className="text-slate-500">APPLICANT NAME:</span>
                    <span className="text-slate-300 font-bold">{applicant.extractedPassportDetails?.full_name || "MOHAMED FAZAL"}</span>
                  </div>
                  <div className="flex justify-between border-b border-slate-900 pb-1.5">
                    <span className="text-slate-500">PASSPORT NO:</span>
                    <span className="text-cyan-400 font-bold">{applicant.extractedPassportDetails?.passport_number || "N1234567"}</span>
                  </div>
                  <div className="flex justify-between border-b border-slate-900 pb-1.5">
                    <span className="text-slate-500">HOME COUNTRY:</span>
                    <span className="text-slate-300">{applicant.extractedAddressDetails?.home_country || applicant.home_country || "Sri Lanka"}</span>
                  </div>
                  <div className="flex justify-between border-b border-slate-900 pb-1.5">
                    <span className="text-slate-500">HOST TYPE / HOTEL:</span>
                    <span className="text-amber-400 font-bold">{applicant.extractedHostDetails?.hotel_name || "Grand Palace Hotel, Bucharest"}</span>
                  </div>
                  <div className="flex justify-between text-[10px] text-slate-500 italic mt-1 leading-relaxed">
                    💡 Form-filling reads straight from OCR Extraction databases! Adjust details inside the "Simulated Extractor" or "Applicant Schematics" tabs.
                  </div>
                </div>
              </div>

              {/* Cloud Terminal Terminal console */}
              <div className="bg-slate-900 border border-slate-800 rounded-2xl flex flex-col flex-1 overflow-hidden shadow-2xl min-h-[350px]">
                <div className="bg-slate-950 px-4 py-3 border-b border-slate-800 flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <Terminal className="w-4 h-4 text-cyan-400 animate-pulse" />
                    <span className="text-xs font-bold text-slate-300">Cloud Sandbox Agent Console Logs</span>
                  </div>
                  {cloudStatus !== "running" && cloudStatus !== "loading" && (
                    <button
                      onClick={handleLaunchCloudAgent}
                      className="px-2.5 py-1 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-[10px] font-bold transition-all shadow-md active:scale-95 cursor-pointer flex items-center space-x-1 shrink-0"
                    >
                      <PlayCircle className="w-3 h-3 text-white" />
                      <span>Launch Browser</span>
                    </button>
                  )}
                </div>

                <div ref={cloudLogContainerRef} className="flex-1 overflow-y-auto bg-slate-950/80 p-4 font-mono text-[11px] space-y-3.5 max-h-[400px]">
                  {cloudLogs.map((log, index) => (
                    <div key={index} className="flex items-start space-x-3 leading-relaxed">
                      <span className="text-slate-500 whitespace-nowrap">{log.timestamp}</span>
                      <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold uppercase tracking-wider whitespace-nowrap ${
                        log.status === "success" ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" :
                        log.status === "error" ? "bg-rose-500/10 text-rose-400 border border-rose-500/20" :
                        log.status === "warning" ? "bg-amber-500/10 text-amber-400 border border-amber-500/20" :
                        "bg-slate-800 text-slate-300 border border-slate-700"
                      }`}>
                        {log.stage}
                      </span>
                      <span className={
                        log.status === "success" ? "text-emerald-300" :
                        log.status === "error" ? "text-rose-300 font-semibold" :
                        log.status === "warning" ? "text-amber-300" :
                        "text-slate-300"
                      }>
                        {log.message}
                      </span>
                    </div>
                  ))}
                  <div ref={cloudLogEndRef} />
                </div>
              </div>

            </div>

          </div>
        </div>
      )}

      {/* LOCAL PYTHON AGENT MONITORING PANEL */}
      {agentMode === "local" && (
        <div className="space-y-6">
          {/* Top Banner Controls */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center space-x-4">
              <div className="p-3 bg-cyan-500/10 rounded-xl border border-cyan-500/20 text-cyan-400">
                <Cpu className="w-6 h-6 animate-pulse" />
              </div>
              <div>
                <div className="flex items-center space-x-3">
                  <h2 className="text-lg font-bold text-slate-100">AI Local Browser Agent Workspace</h2>
                  {getStatusBadge(localSession.status)}
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  Synchronize your real Chrome instance with the Romania e-Visa website and monitor automation live from this console.
                </p>
              </div>
            </div>

            <div className="flex items-center space-x-3 w-full md:w-auto">
              <button
                onClick={handleResetSession}
                className="flex-1 md:flex-none inline-flex items-center justify-center space-x-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-xl text-xs font-semibold text-slate-300 transition-all active:scale-95 cursor-pointer"
              >
                <RefreshCw className="w-4 h-4 text-slate-400" />
                <span>Reset View</span>
              </button>

              <button
                onClick={handleDownloadAgent}
                disabled={isDownloading}
                className="flex-1 md:flex-none inline-flex items-center justify-center space-x-2 px-5 py-2.5 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white rounded-xl text-xs font-bold transition-all shadow-lg shadow-cyan-900/20 active:scale-95 cursor-pointer"
              >
                {isDownloading ? (
                  <RefreshCw className="w-4 h-4 animate-spin text-white" />
                ) : (
                  <Download className="w-4 h-4 text-white" />
                )}
                <span>Get Live-Sync Python Agent</span>
              </button>
            </div>
          </div>

          {/* Main Grid Workspace */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            
            {/* Left Side: Real Chrome Browser Stream / Instruction Map */}
            <div className="lg:col-span-7 flex flex-col space-y-4">
              <div className="bg-slate-900 border border-slate-800 rounded-2xl flex flex-col flex-1 overflow-hidden shadow-2xl">
                {/* Simulated Browser Bar */}
                <div className="bg-slate-950 px-4 py-3 border-b border-slate-800 flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <span className="w-3 h-3 rounded-full bg-rose-500"></span>
                    <span className="w-3 h-3 rounded-full bg-amber-500"></span>
                    <span className="w-3 h-3 rounded-full bg-emerald-500"></span>
                  </div>
                  
                  <div className="flex items-center space-x-2 bg-slate-900 px-3 py-1 rounded-lg border border-slate-800 w-1/2 justify-center">
                    <Globe className="w-3 h-3 text-slate-400 mr-1.5" />
                    <span className="text-xs font-mono text-slate-300 overflow-hidden text-ellipsis whitespace-nowrap">
                      https://evisa.mae.ro/eVisa/Draft
                    </span>
                  </div>

                  <div className="flex items-center space-x-2 text-xs text-slate-500">
                    <span className="bg-cyan-500/10 text-cyan-400 text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-wider animate-pulse">
                      LOCAL PORT SYNC
                    </span>
                  </div>
                </div>

                {/* Browser Window Viewport Content */}
                <div className="relative flex-1 bg-slate-950 min-h-[450px] max-h-[650px] overflow-auto flex items-center justify-center p-4">
                  {localSession.screenshot ? (
                    <div className="relative group rounded-lg overflow-hidden border border-slate-800 shadow-2xl max-w-full">
                      <img
                        src={localSession.screenshot}
                        alt="Real Local Chrome Session Screenshot"
                        className="object-contain max-h-[580px] w-full"
                        referrerPolicy="no-referrer"
                      />
                      <div className="absolute inset-0 bg-slate-950/20 pointer-events-none group-hover:bg-transparent transition-all"></div>
                      
                      {/* Status Overlay Tag */}
                      <div className="absolute bottom-4 left-4 bg-slate-950/80 backdrop-blur-md px-3 py-1.5 rounded-lg border border-slate-800/80 flex items-center space-x-2 text-xs text-slate-300">
                        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
                        <span>Live Chrome Output ({localSession.currentStage})</span>
                      </div>
                    </div>
                  ) : (
                    <div className="text-center max-w-md p-6 space-y-6">
                      <div className="mx-auto w-16 h-16 rounded-full bg-slate-900 border border-slate-800 flex items-center justify-center text-slate-400 animate-pulse">
                        <Eye className="w-8 h-8 text-cyan-400" />
                      </div>
                      <div>
                        <h3 className="text-sm font-bold text-slate-200">Awaiting Local Browser Sync...</h3>
                        <p className="text-xs text-slate-400 mt-2 leading-relaxed">
                          This panel streams your real local computer's Chrome browser viewport automatically while your python selenium filling agent runs.
                        </p>
                      </div>

                      <div className="bg-slate-900/50 border border-slate-800/60 rounded-xl p-4 text-left space-y-3">
                        <h4 className="text-xs font-bold text-cyan-400 uppercase tracking-wider">How to Connect Local Driver:</h4>
                        <ol className="list-decimal list-inside text-[11px] text-slate-300 space-y-2 leading-relaxed">
                          <li>
                            Download the <span className="text-cyan-400 font-semibold cursor-pointer underline" onClick={handleDownloadAgent}>Live-Sync Python Agent</span> script using the button above.
                          </li>
                          <li>
                            Launch Chrome in debug mode on port <span className="font-mono text-amber-400 bg-slate-950 px-1 py-0.2 rounded">9222</span> (or run the generated <span className="font-mono text-emerald-400">.bat</span> loader).
                          </li>
                          <li>
                            Navigate to the Romanian e-Visa website in that Chrome window.
                          </li>
                          <li>
                            Execute: <code className="font-mono text-cyan-300 text-[10px] bg-slate-950 p-1 rounded">python run_evisa_automation_live_sync.py</code>.
                          </li>
                          <li>
                            Watch the visual pipeline execute and report logs!
                          </li>
                        </ol>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Right Side: Brain Activity & Execution Timeline */}
            <div className="lg:col-span-5 flex flex-col space-y-4">
              
              {/* Active Brain Reasoner Card */}
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-2xl flex flex-col space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold text-cyan-400 uppercase tracking-wider flex items-center space-x-1.5">
                    <Activity className="w-4 h-4 text-cyan-400" />
                    <span>Local Agent Reasoning Engine</span>
                  </h3>
                  <span className="text-[10px] font-mono text-slate-500 bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
                    Active Stage: {localSession.currentStage}
                  </span>
                </div>

                <div className="bg-slate-950 rounded-xl p-4 border border-slate-800/80">
                  <p className="text-xs font-mono text-slate-300 leading-relaxed italic">
                    &ldquo;{localSession.message}&rdquo;
                  </p>
                  {localSession.timestamp && (
                    <p className="text-[10px] text-slate-500 font-mono mt-2 text-right">
                      Last Update: {new Date(localSession.timestamp).toLocaleTimeString()}
                    </p>
                  )}
                </div>
              </div>

              {/* Real-time Logs Terminal */}
              <div className="bg-slate-900 border border-slate-800 rounded-2xl flex flex-col flex-1 overflow-hidden shadow-2xl min-h-[300px]">
                <div className="bg-slate-950 px-4 py-3 border-b border-slate-800 flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <Terminal className="w-4 h-4 text-emerald-400" />
                    <span className="text-xs font-bold text-slate-300">Live Execution Log Timeline</span>
                  </div>
                  <button
                    onClick={() => {
                      setLocalSession(prev => ({
                        ...prev,
                        logs: [{
                          timestamp: new Date().toLocaleTimeString(),
                          stage: "SYSTEM",
                          status: "info",
                          message: "Logs cleared by user."
                        }]
                      }));
                    }}
                    className="text-[10px] font-semibold text-slate-400 hover:text-slate-200"
                  >
                    Clear logs
                  </button>
                </div>

                <div ref={localLogContainerRef} className="flex-1 overflow-y-auto bg-slate-950/80 p-4 font-mono text-xs space-y-3.5 max-h-[400px]">
                  {localSession.logs.map((log, index) => (
                    <div key={index} className="flex items-start space-x-3 text-[11px] leading-relaxed">
                      <span className="text-slate-500 whitespace-nowrap">{log.timestamp}</span>
                      <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold uppercase tracking-wider whitespace-nowrap ${
                        log.status === "success" ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" :
                        log.status === "error" ? "bg-rose-500/10 text-rose-400 border border-rose-500/20" :
                        log.status === "warning" ? "bg-amber-500/10 text-amber-400 border border-amber-500/20" :
                        "bg-slate-800 text-slate-300 border border-slate-700"
                      }`}>
                        {log.stage}
                      </span>
                      <span className={
                        log.status === "success" ? "text-emerald-300" :
                        log.status === "error" ? "text-rose-300 font-semibold" :
                        log.status === "warning" ? "text-amber-300" :
                        "text-slate-300"
                      }>
                        {log.message}
                      </span>
                    </div>
                  ))}
                  <div ref={logEndRef} />
                </div>
              </div>

            </div>

          </div>
        </div>
      )}

      {/* Text Inspection & Word Selection Modal / Drawer */}
      {isInspectTextOpen && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-md flex items-center justify-center p-4 sm:p-6 overflow-y-auto">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-3xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh]">
            
            {/* Modal Header */}
            <div className="bg-slate-950 px-5 py-4 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center space-x-2.5">
                <div className="p-2 rounded-lg bg-purple-500/10 border border-purple-500/30 text-purple-400">
                  <FileText className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-100">Sandbox Page Text & Word Selector</h3>
                  <p className="text-[11px] text-slate-400">
                    Highlight and select any text directly, or click a word chip to copy to clipboard instantly.
                  </p>
                </div>
              </div>

              <div className="flex items-center space-x-2">
                <button
                  onClick={handleFetchPageText}
                  disabled={inspectLoading}
                  className="p-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-lg text-slate-300 text-xs font-semibold flex items-center space-x-1 cursor-pointer"
                  title="Refresh page text"
                >
                  <RotateCw className={`w-3.5 h-3.5 ${inspectLoading ? 'animate-spin text-purple-400' : ''}`} />
                  <span className="hidden sm:inline">Refresh Text</span>
                </button>
                <button
                  onClick={() => setIsInspectTextOpen(false)}
                  className="p-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-lg text-slate-400 hover:text-slate-100 cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Notification Banner */}
            {copiedSuccess && (
              <div className="bg-emerald-500/15 border-b border-emerald-500/30 px-5 py-2 flex items-center justify-between text-xs text-emerald-300 font-semibold animate-pulse">
                <div className="flex items-center space-x-2">
                  <Check className="w-4 h-4 text-emerald-400" />
                  <span>{copiedSuccess}</span>
                </div>
              </div>
            )}

            {/* Modal Body */}
            <div className="p-5 overflow-y-auto space-y-5 flex-1 font-sans">
              
              {inspectLoading ? (
                <div className="py-16 text-center space-y-3">
                  <RefreshCw className="w-8 h-8 text-purple-400 animate-spin mx-auto" />
                  <p className="text-xs text-slate-400 font-mono">Extracting text elements from active E-Visa portal page...</p>
                </div>
              ) : (
                <>
                  {/* Selectable Full Text Area */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-bold text-purple-300 uppercase tracking-wider flex items-center space-x-1.5">
                        <FileText className="w-3.5 h-3.5 text-purple-400" />
                        <span>Selectable Page Text (Highlight & Copy):</span>
                      </label>
                      <button
                        onClick={() => copyToClipboard(extractedText, "Entire Page Text")}
                        className="px-2.5 py-1 bg-purple-600/30 hover:bg-purple-600/50 text-purple-300 border border-purple-500/30 rounded-lg text-[11px] font-semibold flex items-center space-x-1 cursor-pointer transition-all"
                      >
                        <Copy className="w-3 h-3" />
                        <span>Copy All Text</span>
                      </button>
                    </div>

                    <textarea
                      value={extractedText}
                      readOnly
                      rows={8}
                      className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs font-mono text-slate-200 focus:outline-none focus:border-purple-500/50 leading-relaxed select-all"
                      placeholder="No text extracted from current page."
                    />
                  </div>

                  {/* 1-Click Word Chips Selector */}
                  {extractedWords.length > 0 && (
                    <div className="space-y-2.5">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-bold text-cyan-300 uppercase tracking-wider flex items-center space-x-1.5">
                          <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                          <span>1-Click Word Selector Bank (Click word to copy):</span>
                        </label>
                        <div className="relative">
                          <Search className="w-3 h-3 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
                          <input
                            type="text"
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            placeholder="Filter words..."
                            className="bg-slate-950 border border-slate-800 rounded-lg pl-7 pr-2.5 py-1 text-[11px] text-slate-200 placeholder-slate-600 focus:outline-none focus:border-cyan-500"
                          />
                        </div>
                      </div>

                      <div className="flex flex-wrap gap-1.5 max-h-48 overflow-y-auto p-2 bg-slate-950 border border-slate-800/80 rounded-xl">
                        {extractedWords
                          .filter(w => !searchTerm || w.toLowerCase().includes(searchTerm.toLowerCase()))
                          .map((word, idx) => (
                            <button
                              key={idx}
                              onClick={() => copyToClipboard(word, `Word "${word}"`)}
                              className="px-2.5 py-1 bg-slate-900 hover:bg-cyan-950 hover:text-cyan-300 text-slate-300 border border-slate-800 hover:border-cyan-500/50 rounded-lg text-[11px] font-mono transition-all flex items-center space-x-1 cursor-pointer active:scale-95"
                            >
                              <span>{word}</span>
                              <Copy className="w-2.5 h-2.5 opacity-40 hover:opacity-100" />
                            </button>
                          ))}
                      </div>
                    </div>
                  )}

                  {/* Form Field Inspector Values */}
                  {extractedFields.length > 0 && (
                    <div className="space-y-2">
                      <label className="text-xs font-bold text-emerald-300 uppercase tracking-wider flex items-center space-x-1.5">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                        <span>Form Input Fields Detected ({extractedFields.length}):</span>
                      </label>
                      <div className="bg-slate-950 border border-slate-800/80 rounded-xl p-3 space-y-2 max-h-40 overflow-y-auto">
                        {extractedFields.map((f, i) => (
                          <div key={i} className="flex items-center justify-between text-xs font-mono border-b border-slate-900 pb-1.5 last:border-0 last:pb-0">
                            <span className="text-slate-400">{f.name || 'Input'}:</span>
                            <div className="flex items-center space-x-2">
                              <span className="text-emerald-300 bg-slate-900 px-2 py-0.5 rounded border border-slate-800">
                                {f.value || '<empty>'}
                              </span>
                              {f.value && (
                                <button
                                  onClick={() => copyToClipboard(f.value, f.name)}
                                  className="text-slate-500 hover:text-cyan-300 cursor-pointer p-0.5"
                                  title="Copy field value"
                                >
                                  <Copy className="w-3 h-3" />
                                </button>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}

            </div>

            {/* Modal Footer */}
            <div className="bg-slate-950 px-5 py-3 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
              <span className="font-mono text-[11px]">Click outside or press Close to resume interactive sandbox view.</span>
              <button
                onClick={() => setIsInspectTextOpen(false)}
                className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-bold transition-all cursor-pointer"
              >
                Close Inspector
              </button>
            </div>

          </div>
        </div>
      )}

    </div>
  );
};
