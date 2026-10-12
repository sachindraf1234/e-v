import React, { useState } from "react";
import { Header } from "./components/Header";
import { PipelineVisualizer } from "./components/PipelineVisualizer";
import { ApplicantSchematicsEditor } from "./components/ApplicantSchematicsEditor";
import { AiDocumentExtractor } from "./components/AiDocumentExtractor";
import { SupportingDocsManager } from "./components/SupportingDocsManager";
import { PythonCodeGenerator } from "./components/PythonCodeGenerator";
import { ConsoleSimulator } from "./components/ConsoleSimulator";
import { XPathInspector } from "./components/XPathInspector";
import { RealTimeBrowserAgent } from "./components/RealTimeBrowserAgent";

import { ApplicantRecord, AutomationConfig, AutomationLog, TargetStageMode } from "./types";
import { DEFAULT_AUTOMATION_CONFIG, INITIAL_APPLICANT_RECORD } from "./data/initialData";

export function App() {
  const [applicant, setApplicant] = useState<ApplicantRecord>(INITIAL_APPLICANT_RECORD);
  const [config, setConfig] = useState<AutomationConfig>(DEFAULT_AUTOMATION_CONFIG);
  const [activeTab, setActiveTab] = useState<"schematics" | "extractor" | "documents" | "code" | "console" | "xpaths" | "agent">("agent");
  const [isSimulating, setIsSimulating] = useState<boolean>(false);
  const [activeStageIndex, setActiveStageIndex] = useState<number>(7); // Default to Home Address Block

  const [logs, setLogs] = useState<AutomationLog[]>([
    {
      id: "log-0",
      timestamp: new Date().toLocaleTimeString(),
      stage: "CONNECTIVITY",
      status: "info",
      message: "Studio Engine Ready. Remote Debugging Target: 127.0.0.1:9222",
    },
    {
      id: "log-1",
      timestamp: new Date().toLocaleTimeString(),
      stage: "SYSTEM",
      status: "success",
      message: `File Number loaded: ${INITIAL_APPLICANT_RECORD.fileNumber} (${INITIAL_APPLICANT_RECORD.personalData.surname} ${INITIAL_APPLICANT_RECORD.personalData.first_names})`,
    },
  ]);

  const handleClearLogs = () => {
    setLogs([]);
  };

  const handleRunSimulation = async () => {
    setIsSimulating(true);
    setActiveTab("console");

    const addLog = (
      stage: TargetStageMode | "SYSTEM" | "CONNECTIVITY",
      status: "info" | "success" | "warning" | "error",
      message: string,
      xpath?: string
    ) => {
      setLogs((prev) => [
        ...prev,
        {
          id: `log-${Date.now()}-${Math.random()}`,
          timestamp: new Date().toLocaleTimeString(),
          stage,
          status,
          message,
          xpath,
        },
      ]);
    };

    addLog("CONNECTIVITY", "info", `Connecting Selenium to active browser tab on ${config.chromeHost}:${config.chromePort}...`);
    await new Promise((r) => setTimeout(r, 600));

    addLog("CONNECTIVITY", "success", "Chrome CDP Session Connected! Active URL: https://evisa.mae.ro/eVisa/Draft");
    await new Promise((r) => setTimeout(r, 500));

    addLog("SYSTEM", "info", "Executing session validity scan ('Your session has expired' / 'Sesiunea dumneavoastră a expirat')...");
    await new Promise((r) => setTimeout(r, 400));
    addLog("SYSTEM", "success", "Session valid. No expiration overlay detected.");

    // Stage 1: Home Address
    setActiveStageIndex(7);
    addLog("APPLICANT_HOME_ADDRESS", "info", "Processing: Applicant's Home Address Workflow Stage...");
    await new Promise((r) => setTimeout(r, 400));

    addLog(
      "APPLICANT_HOME_ADDRESS",
      "info",
      `Setting dropdown 'Home country' directly to: '${applicant.addressData.home_country}'`,
      "//select[contains(@id, 'Home country')] | //label[contains(., 'Home country')]/following-sibling::select"
    );
    await new Promise((r) => setTimeout(r, 300));

    addLog(
      "APPLICANT_HOME_ADDRESS",
      "info",
      `Place field populated: '${applicant.addressData.place}'`,
      "//label[contains(., 'Place')]/following-sibling::input"
    );
    await new Promise((r) => setTimeout(r, 300));

    addLog(
      "APPLICANT_HOME_ADDRESS",
      "info",
      `Address target string injected: '${applicant.addressData.address}'`,
      "//label[contains(., 'Address')]/following-sibling::textarea"
    );
    await new Promise((r) => setTimeout(r, 300));

    addLog("APPLICANT_HOME_ADDRESS", "info", "Initiating reliable page saving sequence...");
    await new Promise((r) => setTimeout(r, 400));
    addLog("APPLICANT_HOME_ADDRESS", "success", "Page refresh complete. Address elements synced.");

    // Stage 2: Host Details
    setActiveStageIndex(8);
    addLog("HOST_DETAILS", "info", "Processing: Details Regarding The Host Workflow Stage...");
    await new Promise((r) => setTimeout(r, 400));

    addLog(
      "HOST_DETAILS",
      "info",
      `Type of host selected: '${applicant.hostData.type_of_host}'`,
      "//select[contains(@id, 'Type of host')]"
    );
    await new Promise((r) => setTimeout(r, 300));

    addLog(
      "HOST_DETAILS",
      "info",
      `Hotel name injected: '${applicant.hostData.hotel_name}'`,
      "//label[contains(., 'Hotel name')]/following-sibling::input"
    );
    await new Promise((r) => setTimeout(r, 300));

    addLog("HOST_DETAILS", "success", "Host details stage workflow completely finished!");

    // Stage 3: Company Contact Details
    setActiveStageIndex(9);
    addLog("COMPANY_CONTACT", "info", "Processing: Company Contact Details Stage...");
    await new Promise((r) => setTimeout(r, 400));
    addLog(
      "COMPANY_CONTACT",
      "info",
      `Company name injected: '${applicant.companyContactData.name}', Work Permit #: '${applicant.companyContactData.work_permit_number}'`,
      "//label[contains(., 'Company name')]/following-sibling::input"
    );
    await new Promise((r) => setTimeout(r, 300));
    addLog("COMPANY_CONTACT", "success", "Company contact stage workflow completely finished!");

    // Stage 4: Visa Requested Details
    setActiveStageIndex(10);
    addLog("DETAILS_ABOUT_VISA", "info", "Processing: Details About Visa Requested Stage...");
    await new Promise((r) => setTimeout(r, 400));
    addLog(
      "DETAILS_ABOUT_VISA",
      "info",
      `Main destination: '${applicant.visaRequestedDetails.main_destination}', Number of entries: '${applicant.visaRequestedDetails.number_of_entries}'`,
      "//label[contains(., 'Main destination')]/following-sibling::input"
    );
    await new Promise((r) => setTimeout(r, 300));
    addLog("DETAILS_ABOUT_VISA", "success", "Visa requested details stage finished!");

    // Stage 5: Cost and Means of Support
    setActiveStageIndex(11);
    addLog("COST_AND_MEANS", "info", "Processing: Cost and Means of Support Stage...");
    await new Promise((r) => setTimeout(r, 400));
    addLog(
      "COST_AND_MEANS",
      "info",
      `Cost covered by: '${applicant.costAndMeansData.cost_covered_by}', Insurance until: '${applicant.costAndMeansData.insurance_valid_until}'`,
      "//select[contains(@id, 'Cost covered by')]"
    );
    await new Promise((r) => setTimeout(r, 300));
    addLog("COST_AND_MEANS", "success", "Cost & Means stage workflow finished!");

    // Stage 6: Family Details
    setActiveStageIndex(12);
    addLog("FAMILY_DETAILS", "info", `Processing Family Details Stage (Civil Status: ${applicant.applicant_civil_status})...`);
    await new Promise((r) => setTimeout(r, 400));

    if (applicant.applicant_civil_status === "Married") {
      addLog(
        "FAMILY_DETAILS",
        "info",
        `Spouse details injected: ${applicant.spouseData.spouse_surname} ${applicant.spouseData.spouse_first_names}`,
        "//label[contains(., 'Surname of spouse')]/following-sibling::input"
      );
      await new Promise((r) => setTimeout(r, 300));
    }

    addLog("FAMILY_DETAILS", "success", "Family details stage workflow completely finished!");

    // Stage 7: Details Regarding Journey
    setActiveStageIndex(13);
    addLog("DETAILS_REGARDING_JOURNEY", "info", "Processing: Details Regarding Journey Stage...");
    await new Promise((r) => setTimeout(r, 400));
    addLog(
      "DETAILS_REGARDING_JOURNEY",
      "info",
      `Arrival: ${applicant.journeyDetailsData.arrival_date}, Departure: ${applicant.journeyDetailsData.departure_date}, Border Post: ${applicant.journeyDetailsData.border_post}`,
      "//input[contains(@id, 'arrival_date')]"
    );
    await new Promise((r) => setTimeout(r, 300));
    addLog("DETAILS_REGARDING_JOURNEY", "success", "Journey details stage workflow finished!");

    // Stage 8: Documents Upload
    setActiveStageIndex(15);
    addLog("DOCUMENTS_UPLOAD", "info", "Processing Supporting Documents Pipeline (6 attachments)...");
    await new Promise((r) => setTimeout(r, 400));

    applicant.documents.forEach((doc) => {
      addLog("DOCUMENTS_UPLOAD", "success", `Document verified & attached: ${doc.requiredCode} (${doc.fileSizeMb} MB)`);
    });

    // Stage 9: Summary File Stage
    setActiveStageIndex(16);
    addLog("SUMMARY_FILE", "info", "Awaiting final review & submit confirmation on summary page...");
    await new Promise((r) => setTimeout(r, 400));
    addLog("SUMMARY_FILE", "success", "Summary page verified. All 17 E-Visa application stages complete!");

    addLog("SYSTEM", "success", "FULL PIPELINE AUTOMATION SIMULATION COMPLETED SUCCESSFULLY!");
    setIsSimulating(false);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-cyan-500 selection:text-slate-950">
      {/* Top Navigation Header */}
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        targetMode={config.targetMode}
        setTargetMode={(mode) => setConfig({ ...config, targetMode: mode })}
        fileNumber={applicant.fileNumber}
        onRunSimulation={handleRunSimulation}
        isSimulating={isSimulating}
      />

      {/* Main Workspace Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* 12-Stage Visual Pipeline Bar */}
        <PipelineVisualizer
          currentTargetMode={config.targetMode}
          onSelectStage={(stage) => setConfig({ ...config, targetMode: stage })}
          activeStageIndex={activeStageIndex}
          applicant={applicant}
        />

        {/* Dynamic Tab Content */}
        {activeTab === "schematics" && (
          <ApplicantSchematicsEditor applicant={applicant} onUpdateApplicant={setApplicant} />
        )}

        {activeTab === "extractor" && (
          <AiDocumentExtractor applicant={applicant} onUpdateApplicant={setApplicant} />
        )}

        {activeTab === "documents" && (
          <SupportingDocsManager applicant={applicant} onUpdateApplicant={setApplicant} />
        )}

        {activeTab === "code" && (
          <PythonCodeGenerator applicant={applicant} config={config} onUpdateConfig={setConfig} />
        )}

        {activeTab === "agent" && (
          <RealTimeBrowserAgent applicant={applicant} config={config} />
        )}

        {activeTab === "console" && (
          <ConsoleSimulator
            logs={logs}
            onClearLogs={handleClearLogs}
            onRunSimulation={handleRunSimulation}
            isSimulating={isSimulating}
            targetMode={config.targetMode}
          />
        )}

        {activeTab === "xpaths" && <XPathInspector />}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900 bg-slate-950 py-4 text-center text-xs text-slate-500">
        <p>
          E-VISA Automation Pipeline Studio &copy; 2026 | Powered by Google Gemini 3.6 Flash &amp; Selenium Remote CDP 127.0.0.1:9222
        </p>
      </footer>
    </div>
  );
}

export default App;
