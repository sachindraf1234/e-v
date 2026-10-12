import React, { useState, useEffect } from "react";
import { Code, Copy, Download, Check, Settings, RefreshCw, ShieldCheck, FileCode } from "lucide-react";
import { ApplicantRecord, AutomationConfig, TargetStageMode } from "../types";

interface PythonCodeGeneratorProps {
  applicant: ApplicantRecord;
  config: AutomationConfig;
  onUpdateConfig: (updated: AutomationConfig) => void;
}

export const PythonCodeGenerator: React.FC<PythonCodeGeneratorProps> = ({
  applicant,
  config,
  onUpdateConfig,
}) => {
  const [activeTab, setActiveTab] = useState<
    "playwright_js" | "playwright" | "video_form" | "playwright_full" | "personal_data_txt" | "playwright_txt" | "automation_steps_txt"
  >("playwright");
  const [pythonScript, setPythonScript] = useState<string>("");
  const [playwrightJsScript, setPlaywrightJsScript] = useState<string>("");
  const [playwrightWorkflowScript, setPlaywrightWorkflowScript] = useState<string>("");
  const [videoFormScript, setVideoFormScript] = useState<string>("");
  const [personalDataTxt, setPersonalDataTxt] = useState<string>("");
  const [playwrightTxt, setPlaywrightTxt] = useState<string>("");
  const [automationStepsTxt, setAutomationStepsTxt] = useState<string>("");
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);
  const [showInstructions, setShowInstructions] = useState<boolean>(true);

  const fetchScript = async () => {
    setIsGenerating(true);
    try {
      const response = await fetch("/api/generate-python-script", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ applicant, config }),
      });

      const data = await response.json();
      if (data.success && data.script) {
        setPythonScript(data.script);
      }

      const wfRes = await fetch("/api/workflow-scripts");
      const wfData = await wfRes.json();
      if (wfData.success) {
        if (wfData.playwrightJs) setPlaywrightJsScript(wfData.playwrightJs);
        if (wfData.playwright) setPlaywrightWorkflowScript(wfData.playwright);
        if (wfData.videoForm) setVideoFormScript(wfData.videoForm);
        if (wfData.personalDataTxt) setPersonalDataTxt(wfData.personalDataTxt);
        if (wfData.playwrightTxt) setPlaywrightTxt(wfData.playwrightTxt);
        if (wfData.automationStepsTxt) setAutomationStepsTxt(wfData.automationStepsTxt);
      }
    } catch (err) {
      console.error("Failed to generate script:", err);
    } finally {
      setIsGenerating(false);
    }
  };

  useEffect(() => {
    fetchScript();
  }, [applicant, config]);

  const getActiveCode = () => {
    switch (activeTab) {
      case "playwright_js":
        return playwrightJsScript || "// Loading playwright_visa_workflow.js...";
      case "playwright":
        return playwrightWorkflowScript || "# Loading playwright_visa_workflow.py...";
      case "video_form":
        return videoFormScript || "# Loading video_form_workflow.py...";
      case "personal_data_txt":
        return personalDataTxt || "Loading personal_data_applicant_workflow.txt...";
      case "playwright_txt":
        return playwrightTxt || "Loading playwright_visa_workflow.txt...";
      case "automation_steps_txt":
        return automationStepsTxt || "Loading automation_steps.txt...";
      case "playwright_full":
        return pythonScript || "# Loading full playwright script...";
      default:
        return pythonScript;
    }
  };

  const getActiveFilename = () => {
    switch (activeTab) {
      case "playwright_js":
        return "playwright_visa_workflow.js";
      case "playwright":
        return "playwright_visa_workflow.py";
      case "video_form":
        return "video_form_workflow.py";
      case "personal_data_txt":
        return "personal_data_applicant_workflow.txt";
      case "playwright_txt":
        return "playwright_visa_workflow.txt";
      case "automation_steps_txt":
        return "automation_steps.txt";
      case "playwright_full":
        return `evisa_automation_playwright_${applicant.fileNumber || "E25110721257414"}.py`;
    }
  };

  const handleCopyCode = () => {
    navigator.clipboard.writeText(getActiveCode());
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadActiveFile = () => {
    const element = document.createElement("a");
    const file = new Blob([getActiveCode()], { type: "text/plain" });
    element.href = URL.createObjectURL(file);
    element.download = getActiveFilename();
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };

  const handleDownloadBatFile = () => {
    const fileNum = applicant.fileNumber || "E25110721257414";
    const batContent = `@echo off
title eVisa Romania Automation - [${fileNum}]
color 0A
echo ==============================================================================
echo       eVisa Romania Local Playwright & OpenCV Automation (Windows 1-Click)
echo       Target Applicant File: ${fileNum}
echo ==============================================================================
echo.
echo [1/3] Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Python is not installed or not added to your system PATH!
    echo Please download & install Python from https://www.python.org/
    echo IMPORTANT: Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b
)

echo Python found:
python --version
echo.

echo [2/3] Verifying / Installing required libraries (playwright, opencv-python, numpy, pillow)...
python -m pip install --quiet --upgrade pip
python -m pip install "playwright>=1.45.0,<2.0.0" "python-dotenv>=1.0.0" "opencv-python>=4.8.0" "numpy>=1.24.0" "Pillow>=10.0.0"
echo Installing Chromium browser binaries for Playwright...
python -m playwright install chromium
echo.

echo [3/3] Launching eVisa Romania Automation with OpenCV Photo Calibration...
echo.
if exist "%~dp0playwright_visa_workflow.py" (
    python "%~dp0playwright_visa_workflow.py"
    goto script_done
) else if exist "%~dp0evisa_automation_playwright_${fileNum}.py" (
    python "%~dp0evisa_automation_playwright_${fileNum}.py"
    goto script_done
) else (
    echo Searching for python script in current directory...
    for %%f in ("%~dp0*.py") do (
        python "%%f"
        goto script_done
    )
    echo [ERROR] Could not find python automation script in this folder!
)

:script_done
echo.
echo ==============================================================================
echo   Automation script finished or exited.
echo ==============================================================================
pause
`;
    const element = document.createElement("a");
    const file = new Blob([batContent], { type: "text/plain" });
    element.href = URL.createObjectURL(file);
    element.download = `run_evisa_automation_${fileNum}.bat`;
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 pb-4 border-b border-slate-800">
        <div className="flex items-center space-x-3">
          <div className="p-3 bg-emerald-500/10 text-emerald-400 rounded-xl border border-emerald-500/20">
            <Code className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-100 flex items-center space-x-2">
              <span>e-VISA Complete Workflow Automation Scripts</span>
              <span className="bg-emerald-500/20 text-emerald-300 text-xs px-2 py-0.5 rounded-full font-mono font-semibold">
                Particulars → Host Details → Docs
              </span>
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Automated Playwright (Python &amp; Node.js) routines from Particular Situations, Personal Data, Travel Document, Journey Details, Host Details (Hotel/Person), to Supporting Documents.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleCopyCode}
            className="inline-flex items-center space-x-1.5 px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-xl border border-slate-700 transition-colors"
          >
            {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
            <span>{copied ? "Copied!" : "Copy Active Script"}</span>
          </button>

          <button
            onClick={handleDownloadActiveFile}
            className="inline-flex items-center space-x-1.5 px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-bold rounded-xl border border-slate-700 transition-all active:scale-95"
          >
            <Download className="w-4 h-4 text-cyan-400" />
            <span>Download {getActiveFilename()}</span>
          </button>

          <button
            onClick={handleDownloadBatFile}
            className="inline-flex items-center space-x-1.5 px-3.5 py-2 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-bold rounded-xl shadow-lg shadow-emerald-900/30 transition-all active:scale-95"
            title="Download 1-Click Windows Batch Launcher"
          >
            <Download className="w-4 h-4" />
            <span>⚡ Download .bat Launcher</span>
          </button>
        </div>
      </div>

      {/* Script Framework Selector Tabs */}
      <div className="flex flex-wrap gap-2 mb-6 p-1.5 bg-slate-950 rounded-xl border border-slate-800">
        <button
          onClick={() => setActiveTab("playwright")}
          className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-xs font-bold transition-all ${
            activeTab === "playwright"
              ? "bg-emerald-500 text-slate-950 shadow-md"
              : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
          }`}
        >
          <Code className="w-4 h-4" />
          <span>Playwright Python (playwright_visa_workflow.py)</span>
        </button>

        <button
          onClick={() => setActiveTab("playwright_js")}
          className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-xs font-bold transition-all ${
            activeTab === "playwright_js"
              ? "bg-emerald-500 text-slate-950 shadow-md"
              : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
          }`}
        >
          <FileCode className="w-4 h-4" />
          <span>Playwright Node.js (playwright_visa_workflow.js)</span>
        </button>

        <button
          onClick={() => setActiveTab("personal_data_txt")}
          className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-xs font-bold transition-all ${
            activeTab === "personal_data_txt"
              ? "bg-cyan-500 text-slate-950 shadow-md"
              : "text-cyan-400 hover:text-cyan-200 hover:bg-slate-900"
          }`}
        >
          <FileCode className="w-4 h-4" />
          <span>📄 Personal Data Text Steps (.txt)</span>
        </button>

        <button
          onClick={() => setActiveTab("playwright_txt")}
          className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-xs font-bold transition-all ${
            activeTab === "playwright_txt"
              ? "bg-cyan-500 text-slate-950 shadow-md"
              : "text-cyan-400 hover:text-cyan-200 hover:bg-slate-900"
          }`}
        >
          <FileCode className="w-4 h-4" />
          <span>📄 Pipeline Text Steps (.txt)</span>
        </button>

        <button
          onClick={() => setActiveTab("automation_steps_txt")}
          className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-xs font-bold transition-all ${
            activeTab === "automation_steps_txt"
              ? "bg-cyan-500 text-slate-950 shadow-md"
              : "text-cyan-400 hover:text-cyan-200 hover:bg-slate-900"
          }`}
        >
          <FileCode className="w-4 h-4" />
          <span>📄 Automation Specs (.txt)</span>
        </button>

        <button
          onClick={() => setActiveTab("video_form")}
          className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-xs font-bold transition-all ${
            activeTab === "video_form"
              ? "bg-emerald-500 text-slate-950 shadow-md"
              : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
          }`}
        >
          <Code className="w-4 h-4" />
          <span>Reusable Module (video_form_workflow.py)</span>
        </button>

        <button
          onClick={() => setActiveTab("playwright_full")}
          className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-xs font-bold transition-all ${
            activeTab === "playwright_full"
              ? "bg-emerald-500 text-slate-950 shadow-md"
              : "text-slate-400 hover:text-slate-200 hover:bg-slate-900"
          }`}
        >
          <Settings className="w-4 h-4" />
          <span>Full Pipeline Playwright Script</span>
        </button>
      </div>

      {/* How to Run on Currently Open Chrome Guide */}
      <div className="bg-slate-950/80 border border-cyan-500/30 rounded-xl p-4 mb-6 text-xs text-slate-300">
        <div className="flex items-center justify-between mb-2">
          <span className="font-bold text-cyan-400 flex items-center space-x-1.5">
            <span>🚀 Smart Browser Launcher (For transarabianofficial@gmail.com)</span>
          </span>
          <button
            onClick={() => setShowInstructions(!showInstructions)}
            className="text-cyan-400 hover:text-cyan-300 font-semibold"
          >
            {showInstructions ? "Hide Instructions" : "Show Instructions"}
          </button>
        </div>
        {showInstructions && (
          <div className="space-y-2 text-slate-400 mt-2 border-t border-slate-800 pt-3">
            <p><strong className="text-slate-200">How it works:</strong> Choose <strong className="text-emerald-400">Option 1</strong> in the Python script to open Chrome under your <code className="text-cyan-300">transarabianofficial@gmail.com</code> profile.</p>

            <div className="bg-emerald-950/40 border border-emerald-500/20 rounded-lg p-3 my-2 space-y-1.5 text-slate-300">
              <span className="font-bold text-emerald-400 block">💡 FASTEST 1-CLICK WINDOWS LAUNCH:</span>
              <p>1. Click <strong className="text-emerald-400">Download .py Script</strong> and <strong className="text-emerald-400">Download .bat Launcher</strong> (keep both files in your Downloads folder).</p>
              <p>2. Double-click <code className="text-cyan-300">run_evisa_automation_*.bat</code>. It automatically checks Python, installs <code className="text-cyan-300">selenium</code> if missing, and keeps the terminal window open!</p>
            </div>

            <p><strong className="text-slate-200">Step 1 (Paste Applicant Link):</strong> When prompted in the terminal, paste your applicant's unique verification link from their email. Chrome will open directly to the "Access your visa application file" page!</p>
            
            <div className="bg-slate-950 border border-slate-800 rounded-lg p-3 my-2 space-y-1.5 text-slate-300">
              <span className="font-bold text-emerald-400 block">🔑 Step 2: Login & Navigate to 'Summary of Visa Application File' Page</span>
              <p>In your opened Chrome window (<strong>Access your visa application file</strong> page):</p>
              <ul className="list-disc list-inside space-y-1 ml-1 text-slate-400">
                <li>Enter the application <strong className="text-emerald-400">Password</strong>.</li>
                <li>Type the <strong className="text-emerald-400">CAPTCHA text</strong> shown on screen.</li>
                <li>Click <strong className="text-emerald-400">Next &gt;</strong> button to reach the <strong className="text-slate-200">Summary of Visa Application File</strong> page.</li>
              </ul>
            </div>

            <div className="bg-slate-950 border border-slate-800 rounded-lg p-3 my-2 space-y-1.5 text-slate-400">
              <span className="font-bold text-slate-300 block">⚡ Step 3: Press [ENTER] in Terminal to Auto-Click Update & Auto-Fill</span>
              <p>📍 <strong className="text-slate-200">Where to press [ENTER]:</strong> Once you see the <strong className="text-emerald-400">Update visa application</strong> button page, switch to your <strong className="text-cyan-300">Python terminal window (CMD / terminal)</strong>.</p>
              <p>🚀 Press <kbd className="px-1.5 py-0.5 bg-slate-800 text-emerald-400 rounded text-xs font-mono font-bold">ENTER</kbd> in your Python terminal! The terminal will AUTOMATICALLY click <strong className="text-emerald-400">Update visa application</strong> and fill all applicant details automatically!</p>
            </div>

            <div className="bg-amber-950/30 border border-amber-500/30 rounded-lg p-3 my-2 space-y-1.5 text-amber-200 text-xs">
              <span className="font-bold text-amber-400 block">🛠️ TROUBLESHOOTING: "If .py file does not open or closes immediately"</span>
              <p>• <strong>Why this happens:</strong> Double-clicking <code className="text-amber-300">.py</code> directly on Windows closes the terminal window instantly if <code className="text-amber-300">selenium</code> is not installed or if Python file associations are missing.</p>
              <p>• <strong>Solution 1 (Recommended):</strong> Double-click the <strong className="text-emerald-400">run_evisa_automation_*.bat</strong> file instead! It installs dependencies and prevents the window from closing.</p>
              <p>• <strong>Solution 2 (Manual Terminal):</strong> Open <strong className="text-amber-300">Command Prompt (CMD)</strong>, type <code className="text-emerald-300">cd Downloads</code>, type <code className="text-emerald-300">pip install selenium</code>, then type <code className="text-emerald-300">python evisa_automation_*.py</code>.</p>
            </div>
          </div>
        )}
      </div>

      {/* Direct Application Link & Verification Link Configuration Box */}
      <div className="bg-slate-950 border border-emerald-500/30 rounded-xl p-4 mb-6 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-2">
          <div className="flex items-center space-x-2">
            <span className="p-1.5 bg-emerald-500/20 text-emerald-400 rounded-lg">
              <Settings className="w-4 h-4" />
            </span>
            <h3 className="text-xs font-bold uppercase tracking-wider text-emerald-400">
              🔗 Automation Entry Link Configuration (Start Position: Update Button)
            </h3>
          </div>
          <span className="text-[10px] bg-emerald-500/10 text-emerald-300 px-2 py-0.5 rounded border border-emerald-500/20 font-mono">
            Auto-clicks 'Update visa application'
          </span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold text-slate-200 mb-1 flex items-center justify-between">
              <span>🎯 Summary of Visa Application File Link (Target URL)</span>
              <span className="text-[10px] text-emerald-400 font-normal">Starts at 'Update' button</span>
            </label>
            <input
              type="text"
              placeholder="e.g. https://evisa.mae.ro/eVisa/Summary/... or https://evisa.mae.ro/eVisa/Draft"
              value={config.targetApplicationUrl || ""}
              onChange={(e) => onUpdateConfig({ ...config, targetApplicationUrl: e.target.value })}
              className="w-full bg-slate-900 border border-slate-700 focus:border-emerald-500 rounded-xl px-3 py-2 text-xs font-mono text-emerald-300 placeholder-slate-600 focus:outline-none transition-all"
            />
            <p className="text-[11px] text-slate-400 mt-1">
              Paste your application summary URL here. When the script/BAT launcher starts, it automatically navigates here, clicks <strong className="text-emerald-400">Update visa application</strong>, and fills all data!
            </p>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-200 mb-1">
              <span>📧 Email Verification Link (Optional)</span>
            </label>
            <input
              type="text"
              placeholder="e.g. https://evisa.mae.ro/eVisa/Activate/... or verification link"
              value={config.verificationLink || ""}
              onChange={(e) => onUpdateConfig({ ...config, verificationLink: e.target.value })}
              className="w-full bg-slate-900 border border-slate-700 focus:border-cyan-500 rounded-xl px-3 py-2 text-xs font-mono text-cyan-300 placeholder-slate-600 focus:outline-none transition-all"
            />
            <p className="text-[11px] text-slate-400 mt-1">
              Paste the initial email verification link if you want Chrome to open directly to the password + CAPTCHA login page.
            </p>
          </div>
        </div>
      </div>

      {/* CDP Configuration Bar */}
      <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 mb-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div>
          <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">
            Stage Entry Override
          </label>
          <select
            value={config.targetMode}
            onChange={(e) => onUpdateConfig({ ...config, targetMode: e.target.value as TargetStageMode })}
            className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-cyan-300 font-semibold"
          >
            <option value="FULL_PIPELINE">FULL PIPELINE</option>
            <option value="DIPLOMATIC_MISSION">DIPLOMATIC MISSION &amp; DOC TYPE</option>
            <option value="APPLICANT_HOME_ADDRESS">APPLICANT HOME ADDRESS</option>
            <option value="HOST_DETAILS">DETAILS REGARDING HOST</option>
            <option value="FAMILY_DETAILS">APPLICANT FAMILY DETAILS</option>
            <option value="PERSONAL_DATA">PERSONAL DATA</option>
            <option value="DOCUMENTS_UPLOAD">DOCUMENTS UPLOAD</option>
          </select>
        </div>

        <div>
          <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">
            Chrome CDP Address
          </label>
          <input
            type="text"
            value={`${config.chromeHost}:${config.chromePort}`}
            onChange={(e) => {
              const parts = e.target.value.split(":");
              onUpdateConfig({
                ...config,
                chromeHost: parts[0] || "127.0.0.1",
                chromePort: parseInt(parts[1] || "9222", 10),
              });
            }}
            className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs font-mono text-emerald-400"
          />
        </div>

        <div>
          <label className="block text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">
            Element Timeout (Sec)
          </label>
          <input
            type="number"
            value={config.elementWaitTimeoutSec}
            onChange={(e) => onUpdateConfig({ ...config, elementWaitTimeoutSec: parseInt(e.target.value) || 5 })}
            className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs font-mono text-slate-200"
          />
        </div>

        <div className="flex items-center space-x-2 pt-5">
          <input
            type="checkbox"
            id="crashDetect"
            checked={config.crashDetectionEnabled}
            onChange={(e) => onUpdateConfig({ ...config, crashDetectionEnabled: e.target.checked })}
            className="rounded border-slate-700 bg-slate-900 text-cyan-500 focus:ring-cyan-500"
          />
          <label htmlFor="crashDetect" className="text-xs text-slate-300 font-semibold flex items-center space-x-1 cursor-pointer">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span>Session Expiration Crash Guard</span>
          </label>
        </div>
      </div>

      {/* Code Display Area */}
      <div className="relative bg-slate-950 rounded-xl border border-slate-800 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-2.5 bg-slate-900 border-b border-slate-800 text-xs font-mono text-slate-400">
          <div className="flex items-center space-x-2">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-500/80"></span>
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500/80"></span>
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/80"></span>
            <span className="ml-2 text-slate-300 font-bold">
              {getActiveFilename()}
            </span>
          </div>
          {isGenerating && (
            <span className="text-cyan-400 flex items-center space-x-1">
              <RefreshCw className="w-3 h-3 animate-spin" />
              <span>Generating...</span>
            </span>
          )}
        </div>

        <pre className="p-4 text-xs font-mono text-emerald-400 overflow-x-auto max-h-[500px] leading-relaxed">
          {getActiveCode()}
        </pre>
      </div>
    </div>
  );
};
