import React, { useState } from "react";
import { User, MapPin, Building2, Heart, FileText, Check, Save, PhoneCall, Award, Coins, PlaneTakeoff, Briefcase, FolderOpen, HardDrive, ShieldCheck, AlertTriangle, FileUp, RefreshCw } from "lucide-react";
import { ApplicantRecord } from "../types";
import { calculateJourneyAndInsuranceDates } from "../utils/dateCalculations";

export const OTHER_OCCUPATION_PRESETS = [
  "FACTORY HELPER",
  "PACKING HELPER",
  "HANDLER",
  "WAREHOUSE WORKER",
];

export const EVISA_DEFAULT_OCCUPATIONS = [
  { id: "1", label: "Other / Alte ocupații (ID: 1)", code: "Other", needsOtherInput: true },
  { id: "43", label: "Administrative, technical and service staff (ID: 43)", code: "Administrative, technical and service staff", needsOtherInput: false },
  { id: "3", label: "Architect / Arhitect (ID: 3)", code: "Architect", needsOtherInput: false },
  { id: "5", label: "Artisan / Artizan (ID: 5)", code: "Artisan", needsOtherInput: false },
  { id: "4", label: "Artist / Artist (ID: 4)", code: "Artist", needsOtherInput: false },
  { id: "9", label: "Baker / Brutar (ID: 9)", code: "Baker", needsOtherInput: false },
  { id: "6", label: "Banker / Bancher (ID: 6)", code: "Banker", needsOtherInput: false },
  { id: "37", label: "Blue-collar worker / Muncitor (ID: 37)", code: "Blue-collar worker", needsOtherInput: false },
  { id: "39", label: "Businessman / Om de afaceri (ID: 39)", code: "Businessman", needsOtherInput: false },
  { id: "10", label: "Cashier / Casier (ID: 10)", code: "Cashier", needsOtherInput: false },
  { id: "47", label: "Chauffeur, Lorry driver / Șofer (ID: 47)", code: "Chauffeur, Lorry driver", needsOtherInput: false },
  { id: "11", label: "Chemist/Chemical engineer / Chimist (ID: 11)", code: "Chemist/Chemical engineer", needsOtherInput: false },
  { id: "12", label: "Civil Servant / Funcționar public (ID: 12)", code: "Civil Servant", needsOtherInput: false },
  { id: "14", label: "Clerk / Funcționar (ID: 14)", code: "Clerk", needsOtherInput: false },
  { id: "35", label: "Commodity expert / Merceolog (ID: 35)", code: "Commodity expert", needsOtherInput: false },
  { id: "26", label: "Computer expert / Informatician (ID: 26)", code: "Computer expert", needsOtherInput: false },
  { id: "21", label: "Economics profession (accountant) / Economist (ID: 21)", code: "Economics profession (accountant)", needsOtherInput: false },
  { id: "22", label: "Electronics expert / Electronist (ID: 22)", code: "Electronics expert", needsOtherInput: false },
  { id: "27", label: "Engineer / Inginer (ID: 27)", code: "Engineer", needsOtherInput: false },
  { id: "2", label: "Farmer / Agricultor (ID: 2)", code: "Farmer", needsOtherInput: false },
  { id: "50", label: "Fashion, Cosmetics / Stilist/Cosmetician (ID: 50)", code: "Fashion, Cosmetics", needsOtherInput: false },
  { id: "32", label: "Foreman / Maistru (ID: 32)", code: "Foreman", needsOtherInput: false },
  { id: "7", label: "Lawyer / Avocat (ID: 7)", code: "Lawyer", needsOtherInput: false },
  { id: "31", label: "Magistrate / Magistrat (ID: 31)", code: "Magistrate", needsOtherInput: false },
  { id: "33", label: "Manager / Manager (ID: 33)", code: "Manager", needsOtherInput: false },
  { id: "20", label: "Medical/Paramedical (Doctor) / Medic (ID: 20)", code: "Medical/Paramedical (Doctor)", needsOtherInput: false },
  { id: "36", label: "Missionary / Misionar (ID: 36)", code: "Missionary", needsOtherInput: false },
  { id: "40", label: "Operator / Operator (ID: 40)", code: "Operator", needsOtherInput: false },
  { id: "53", label: "Other kind of technician / Tehnician (ID: 53)", code: "Other kind of technician", needsOtherInput: false },
  { id: "41", label: "Pensioner / Pensionar (ID: 41)", code: "Pensioner", needsOtherInput: false },
  { id: "45", label: "Policeman – Soldier / Polițist / Militar (ID: 45)", code: "Policeman – Soldier", needsOtherInput: false },
  { id: "34", label: "Seaman / Marinar (ID: 34)", code: "Seaman", needsOtherInput: false },
  { id: "48", label: "Singer / Solist vocal (ID: 48)", code: "Singer", needsOtherInput: false },
  { id: "49", label: "Sportsperson / Sportiv (ID: 49)", code: "Sportsperson", needsOtherInput: false },
  { id: "51", label: "Student / Elev / Student (ID: 51)", code: "Student", needsOtherInput: false },
  { id: "52", label: "Video surveillance / Supraveghetor video (ID: 52)", code: "Video surveillance", needsOtherInput: false },
  { id: "46", label: "Teacher / Profesor (ID: 46)", code: "Teacher", needsOtherInput: false }
];

export function toMMDDYYYY(raw: string | undefined): string {
  if (!raw) return "";
  const s = raw.trim();
  // If already mm/dd/yyyy or m/d/yyyy
  if (/^\d{1,2}\/\d{1,2}\/\d{4}$/.test(s)) {
    const parts = s.split("/");
    const m = parts[0].padStart(2, "0");
    const d = parts[1].padStart(2, "0");
    return `${m}/${d}/${parts[2]}`;
  }
  // If yyyy-mm-dd
  if (/^\d{4}-\d{1,2}-\d{1,2}$/.test(s)) {
    const [y, m, d] = s.split("-");
    return `${m.padStart(2, "0")}/${d.padStart(2, "0")}/${y}`;
  }
  // Try Date parse
  const dt = new Date(s);
  if (!isNaN(dt.getTime())) {
    const m = String(dt.getMonth() + 1).padStart(2, "0");
    const d = String(dt.getDate()).padStart(2, "0");
    const y = dt.getFullYear();
    return `${m}/${d}/${y}`;
  }
  return s;
}

export function fromMMDDYYYYtoInputDate(raw: string | undefined): string {
  if (!raw) return "";
  const s = raw.trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  if (/^\d{1,2}\/\d{1,2}\/\d{4}$/.test(s)) {
    const parts = s.split("/");
    const m = parts[0].padStart(2, "0");
    const d = parts[1].padStart(2, "0");
    const y = parts[2];
    return `${y}-${m}-${d}`;
  }
  return "";
}

interface ApplicantSchematicsEditorProps {
  applicant: ApplicantRecord;
  onUpdateApplicant: (updated: ApplicantRecord) => void;
}

export const ApplicantSchematicsEditor: React.FC<ApplicantSchematicsEditorProps> = ({
  applicant,
  onUpdateApplicant,
}) => {
  const [activeSubTab, setActiveSubTab] = useState<
    "address" | "host" | "company" | "visa_req" | "cost_means" | "family" | "journey" | "personal" | "passport" | "selection" | "documents_folder"
  >("documents_folder");
  const [savedSuccess, setSavedSuccess] = useState(false);

  const handleSave = () => {
    onUpdateApplicant({
      ...applicant,
      updatedAt: new Date().toISOString(),
    });
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 2500);
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center space-x-2">
            <h2 className="text-lg font-bold text-slate-100">Master Schematics Data Editor</h2>
            <span className="text-xs font-mono px-2.5 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              File #{applicant.fileNumber}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Synchronized variables used by Python Selenium driver during automated E-Visa form execution.
          </p>
        </div>

        <button
          onClick={handleSave}
          className="inline-flex items-center space-x-2 px-4 py-2 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-bold text-xs rounded-xl shadow-lg shadow-cyan-900/30 transition-all active:scale-95 self-start sm:self-auto"
        >
          {savedSuccess ? <Check className="w-4 h-4 text-emerald-300" /> : <Save className="w-4 h-4" />}
          <span>{savedSuccess ? "Saved Master State!" : "Save Changes"}</span>
        </button>
      </div>

      {/* Subtabs for Schematics Sections */}
      <div className="flex space-x-2 border-b border-slate-800/80 mb-6 pb-2 overflow-x-auto no-scrollbar">
        <button
          onClick={() => setActiveSubTab("address")}
          className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
            activeSubTab === "address"
              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <MapPin className="w-3.5 h-3.5" />
          <span>Home Address</span>
        </button>

        <button
          onClick={() => setActiveSubTab("host")}
          className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
            activeSubTab === "host"
              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <Building2 className="w-3.5 h-3.5" />
          <span>Host Details</span>
        </button>

        <button
          onClick={() => setActiveSubTab("company")}
          className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
            activeSubTab === "company"
              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <PhoneCall className="w-3.5 h-3.5" />
          <span>Company Contact</span>
        </button>

        <button
          onClick={() => setActiveSubTab("visa_req")}
          className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
            activeSubTab === "visa_req"
              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <Award className="w-3.5 h-3.5" />
          <span>Visa Requested</span>
        </button>

        <button
          onClick={() => setActiveSubTab("cost_means")}
          className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
            activeSubTab === "cost_means"
              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <Coins className="w-3.5 h-3.5" />
          <span>Cost & Means</span>
        </button>

        <button
          onClick={() => setActiveSubTab("family")}
          className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
            activeSubTab === "family"
              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <Heart className="w-3.5 h-3.5" />
          <span>Family & Spouse</span>
        </button>

        <button
          onClick={() => setActiveSubTab("journey")}
          className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
            activeSubTab === "journey"
              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <PlaneTakeoff className="w-3.5 h-3.5" />
          <span>Journey Details</span>
        </button>

        <button
          onClick={() => setActiveSubTab("personal")}
          className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
            activeSubTab === "personal"
              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <User className="w-3.5 h-3.5" />
          <span>Personal Bio</span>
        </button>

        <button
          onClick={() => setActiveSubTab("passport")}
          className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
            activeSubTab === "passport"
              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <FileText className="w-3.5 h-3.5" />
          <span>Passport & Job</span>
        </button>

        <button
          onClick={() => setActiveSubTab("selection")}
          className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
            activeSubTab === "selection"
              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <FileText className="w-3.5 h-3.5 text-purple-400" />
          <span>Visa Category & Mission</span>
        </button>

        <button
          onClick={() => setActiveSubTab("documents_folder")}
          className={`flex items-center space-x-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all whitespace-nowrap ${
            activeSubTab === "documents_folder"
              ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <FolderOpen className="w-3.5 h-3.5 text-emerald-400" />
          <span>Supporting Documents Folder</span>
        </button>
      </div>

      {/* SECTION 1: HOME ADDRESS */}
      {activeSubTab === "address" && (
        <div className="space-y-4">
          <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800">
            <h3 className="text-xs font-bold uppercase tracking-wider text-cyan-400 mb-4 flex items-center space-x-2">
              <MapPin className="w-4 h-4" />
              <span>BLOCK 1: Applicant's Home Address Pipeline</span>
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Home Country</label>
                <input
                  type="text"
                  value={applicant.addressData.home_country}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      addressData: { ...applicant.addressData, home_country: e.target.value },
                    })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Place (City/District)</label>
                <input
                  type="text"
                  value={applicant.addressData.place}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      addressData: { ...applicant.addressData, place: e.target.value },
                    })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div className="md:col-span-2">
                <label className="block text-xs font-semibold text-slate-300 mb-1">Street Address</label>
                <textarea
                  value={applicant.addressData.address}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      addressData: { ...applicant.addressData, address: e.target.value },
                    })
                  }
                  rows={2}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 2: HOST DETAILS */}
      {activeSubTab === "host" && (
        <div className="space-y-4">
          <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800">
            <h3 className="text-xs font-bold uppercase tracking-wider text-cyan-400 mb-4 flex items-center space-x-2">
              <Building2 className="w-4 h-4" />
              <span>BLOCK 2: Details Regarding The Host Pipeline</span>
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Type of Host</label>
                <select
                  value={applicant.hostData.type_of_host}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      hostData: { ...applicant.hostData, type_of_host: e.target.value },
                    })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                >
                  <option value="Hotel">Hotel</option>
                  <option value="Individual">Individual</option>
                  <option value="Company">Company</option>
                  <option value="Other">Other</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Hotel / Host Name</label>
                <input
                  type="text"
                  value={applicant.hostData.hotel_name}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      hostData: { ...applicant.hostData, hotel_name: e.target.value },
                    })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div className="md:col-span-2">
                <label className="block text-xs font-semibold text-slate-300 mb-1">Host Address in Romania</label>
                <textarea
                  value={applicant.hostData.host_address}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      hostData: { ...applicant.hostData, host_address: e.target.value },
                    })
                  }
                  rows={2}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 2B: COMPANY CONTACT */}
      {activeSubTab === "company" && (
        <div className="space-y-4">
          <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800">
            <h3 className="text-xs font-bold uppercase tracking-wider text-cyan-400 mb-4 flex items-center space-x-2">
              <PhoneCall className="w-4 h-4" />
              <span>BLOCK 2B: Company Contact Data Pipeline</span>
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Company / Host Name</label>
                <input
                  type="text"
                  value={applicant.companyContactData.name}
                  onChange={(e) => {
                    const val = e.target.value;
                    onUpdateApplicant({
                      ...applicant,
                      companyContactData: { ...applicant.companyContactData, name: val },
                      costAndMeansData: { ...applicant.costAndMeansData, host_name: val },
                    });
                  }}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Telephone / Fax</label>
                <input
                  type="text"
                  value={applicant.companyContactData.telephone_fax}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      companyContactData: { ...applicant.companyContactData, telephone_fax: e.target.value },
                    })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Email Address</label>
                <input
                  type="email"
                  value={applicant.companyContactData.email}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      companyContactData: { ...applicant.companyContactData, email: e.target.value },
                    })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Work Permit Number (Aviz)</label>
                <input
                  type="text"
                  value={applicant.companyContactData.work_permit_number}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      companyContactData: { ...applicant.companyContactData, work_permit_number: e.target.value },
                    })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div className="md:col-span-2">
                <label className="block text-xs font-semibold text-slate-300 mb-1">Full Company Address</label>
                <textarea
                  value={applicant.companyContactData.full_address}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      companyContactData: { ...applicant.companyContactData, full_address: e.target.value },
                    })
                  }
                  rows={2}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 2C: VISA REQUESTED DETAILS */}
      {activeSubTab === "visa_req" && (
        <div className="space-y-4">
          <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800">
            <h3 className="text-xs font-bold uppercase tracking-wider text-cyan-400 mb-4 flex items-center space-x-2">
              <Award className="w-4 h-4" />
              <span>BLOCK 2C: Details About Visa Requested Pipeline</span>
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Main Destination</label>
                <input
                  type="text"
                  value={applicant.visaRequestedDetails.main_destination}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      visaRequestedDetails: { ...applicant.visaRequestedDetails, main_destination: e.target.value },
                    })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Number of Entries Requested</label>
                <select
                  value={applicant.visaRequestedDetails.number_of_entries}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      visaRequestedDetails: {
                        ...applicant.visaRequestedDetails,
                        number_of_entries: e.target.value as "1" | "2" | "Multiple",
                      },
                    })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                >
                  <option value="1">1 (Single Entry)</option>
                  <option value="2">2 (Two Entries)</option>
                  <option value="Multiple">Multiple Entries</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Duration of Stay (Days)</label>
                <input
                  type="text"
                  value={applicant.visaRequestedDetails.duration_of_stay}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      visaRequestedDetails: { ...applicant.visaRequestedDetails, duration_of_stay: e.target.value },
                    })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Previous Stays in Romania/Schengen</label>
                <input
                  type="text"
                  value={applicant.visaRequestedDetails.previous_stays}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      visaRequestedDetails: { ...applicant.visaRequestedDetails, previous_stays: e.target.value },
                    })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Means of Transport</label>
                <input
                  type="text"
                  value={applicant.visaRequestedDetails.means_of_transport}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      visaRequestedDetails: { ...applicant.visaRequestedDetails, means_of_transport: e.target.value },
                    })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 2D: COST AND MEANS OF SUPPORT */}
      {activeSubTab === "cost_means" && (
        <div className="space-y-4">
          <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800">
            <h3 className="text-xs font-bold uppercase tracking-wider text-cyan-400 mb-4 flex items-center space-x-2">
              <Coins className="w-4 h-4" />
              <span>BLOCK 2D: Cost and Means of Support Pipeline</span>
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Cost Covered By</label>
                <select
                  value={applicant.costAndMeansData.cost_covered_by}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      costAndMeansData: {
                        ...applicant.costAndMeansData,
                        cost_covered_by: e.target.value as "Myself" | "Host person(s)" | "Host company",
                      },
                    })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                >
                  <option value="Host company">Host company</option>
                  <option value="Host person(s)">Host person(s)</option>
                  <option value="Myself">Myself</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Host Company / Person Name</label>
                <input
                  type="text"
                  value={applicant.costAndMeansData.host_name}
                  onChange={(e) => {
                    const val = e.target.value;
                    onUpdateApplicant({
                      ...applicant,
                      companyContactData: { ...applicant.companyContactData, name: val },
                      costAndMeansData: { ...applicant.costAndMeansData, host_name: val },
                    });
                  }}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Insurance Expiry Date (MM/DD/YYYY)</label>
                <input
                  type="text"
                  placeholder="MM/DD/YYYY"
                  value={applicant.costAndMeansData.insurance_valid_until}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      costAndMeansData: { ...applicant.costAndMeansData, insurance_valid_until: e.target.value },
                    })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div className="md:col-span-2 bg-slate-900/80 p-3 rounded-lg border border-slate-800">
                <label className="block text-xs font-semibold text-slate-300 mb-2">Means of Support Checkboxes</label>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs text-slate-300">
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={applicant.costAndMeansData.means_cash}
                      onChange={(e) =>
                        onUpdateApplicant({
                          ...applicant,
                          costAndMeansData: { ...applicant.costAndMeansData, means_cash: e.target.checked },
                        })
                      }
                      className="rounded bg-slate-950 border-slate-700 text-cyan-500 focus:ring-0"
                    />
                    <span>Cash</span>
                  </label>

                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={applicant.costAndMeansData.means_accommodation}
                      onChange={(e) =>
                        onUpdateApplicant({
                          ...applicant,
                          costAndMeansData: { ...applicant.costAndMeansData, means_accommodation: e.target.checked },
                        })
                      }
                      className="rounded bg-slate-950 border-slate-700 text-cyan-500 focus:ring-0"
                    />
                    <span>Accommodation</span>
                  </label>

                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={applicant.costAndMeansData.means_insurance}
                      onChange={(e) =>
                        onUpdateApplicant({
                          ...applicant,
                          costAndMeansData: { ...applicant.costAndMeansData, means_insurance: e.target.checked },
                        })
                      }
                      className="rounded bg-slate-950 border-slate-700 text-cyan-500 focus:ring-0"
                    />
                    <span>Medical Insurance</span>
                  </label>

                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={applicant.costAndMeansData.means_credit_cards}
                      onChange={(e) =>
                        onUpdateApplicant({
                          ...applicant,
                          costAndMeansData: { ...applicant.costAndMeansData, means_credit_cards: e.target.checked },
                        })
                      }
                      className="rounded bg-slate-950 border-slate-700 text-cyan-500 focus:ring-0"
                    />
                    <span>Credit Cards</span>
                  </label>

                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={applicant.costAndMeansData.means_travellers_cheques}
                      onChange={(e) =>
                        onUpdateApplicant({
                          ...applicant,
                          costAndMeansData: { ...applicant.costAndMeansData, means_travellers_cheques: e.target.checked },
                        })
                      }
                      className="rounded bg-slate-950 border-slate-700 text-cyan-500 focus:ring-0"
                    />
                    <span>Traveller's Cheques</span>
                  </label>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 2E: JOURNEY DETAILS */}
      {activeSubTab === "journey" && (
        <div className="space-y-4">
          <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-cyan-400 flex items-center space-x-2">
                <PlaneTakeoff className="w-4 h-4" />
                <span>BLOCK 2E: Details Regarding Journey Pipeline</span>
              </h3>
              <button
                type="button"
                onClick={() => {
                  const dates = calculateJourneyAndInsuranceDates();
                  onUpdateApplicant({
                    ...applicant,
                    journeyDetailsData: {
                      ...applicant.journeyDetailsData,
                      arrival_date: dates.arrival_date,
                      departure_date: dates.departure_date,
                    },
                    costAndMeansData: {
                      ...applicant.costAndMeansData,
                      insurance_valid_until: dates.insurance_valid_until,
                    },
                  });
                }}
                className="flex items-center space-x-1.5 px-2.5 py-1 rounded bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 text-xs font-mono transition-colors"
                title="Calculate: Arrival = Today's Date of Next Month; Departure = 3 Months from Arrival"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>Auto-Calculate (Next Month + 3 Mos)</span>
              </button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Intended Date of Arrival (MM/DD/YYYY)</label>
                <input
                  type="text"
                  placeholder="MM/DD/YYYY"
                  value={applicant.journeyDetailsData.arrival_date}
                  onChange={(e) => {
                    const val = e.target.value;
                    let autoDep = "";
                    if (/^\d{2}\/\d{2}\/\d{4}$/.test(val)) {
                      const [m, d, y] = val.split("/").map(Number);
                      const arrObj = new Date(y, m - 1, d);
                      if (!isNaN(arrObj.getTime())) {
                        const depTotalMonths = arrObj.getMonth() + 3;
                        const depYear = arrObj.getFullYear() + Math.floor(depTotalMonths / 12);
                        const depMonth = depTotalMonths % 12;
                        const maxDaysDep = new Date(depYear, depMonth + 1, 0).getDate();
                        const depDay = Math.min(arrObj.getDate(), maxDaysDep);
                        const depObj = new Date(depYear, depMonth, depDay);
                        autoDep = `${String(depObj.getMonth() + 1).padStart(2, "0")}/${String(depObj.getDate()).padStart(2, "0")}/${depObj.getFullYear()}`;
                      }
                    }
                    onUpdateApplicant({
                      ...applicant,
                      journeyDetailsData: {
                        ...applicant.journeyDetailsData,
                        arrival_date: val,
                        ...(autoDep ? { departure_date: autoDep } : {}),
                      },
                    });
                  }}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Intended Date of Departure (MM/DD/YYYY)</label>
                <input
                  type="text"
                  placeholder="MM/DD/YYYY"
                  value={applicant.journeyDetailsData.departure_date}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      journeyDetailsData: { ...applicant.journeyDetailsData, departure_date: e.target.value },
                    })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">First Entry State</label>
                <input
                  type="text"
                  value={applicant.journeyDetailsData.first_entry_state}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      journeyDetailsData: { ...applicant.journeyDetailsData, first_entry_state: e.target.value },
                    })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Border Crossing Post</label>
                <input
                  type="text"
                  value={applicant.journeyDetailsData.border_post}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      journeyDetailsData: { ...applicant.journeyDetailsData, border_post: e.target.value },
                    })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Main Destination State</label>
                <input
                  type="text"
                  value={applicant.journeyDetailsData.main_destination_state}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      journeyDetailsData: { ...applicant.journeyDetailsData, main_destination_state: e.target.value },
                    })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Planned Route</label>
                <input
                  type="text"
                  value={applicant.journeyDetailsData.planned_route}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      journeyDetailsData: { ...applicant.journeyDetailsData, planned_route: e.target.value },
                    })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 3: FAMILY & SPOUSE */}
      {activeSubTab === "family" && (
        <div className="space-y-4">
          <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800">
            <h3 className="text-xs font-bold uppercase tracking-wider text-cyan-400 mb-4 flex items-center space-x-2">
              <Heart className="w-4 h-4" />
              <span>BLOCK 3: Applicant's Civil Status & Family Details</span>
            </h3>

            <div className="mb-4">
              <label className="block text-xs font-semibold text-slate-300 mb-1">Applicant Civil Status</label>
              <select
                value={applicant.applicant_civil_status || applicant.personalData?.marital_status || "Single"}
                onChange={(e) => {
                  const val = e.target.value as any;
                  const isSingle = val.toLowerCase().includes("singl") || val === "Single";
                  onUpdateApplicant({
                    ...applicant,
                    applicant_civil_status: isSingle ? "Single" : val,
                    personalData: {
                      ...applicant.personalData,
                      marital_status: isSingle ? "Single" : val,
                    },
                    ...(isSingle ? {
                      spouseData: {
                        spouse_surname: "",
                        spouse_first_names: "",
                        spouse_surname_at_birth: "",
                        spouse_dob_day: "",
                        spouse_dob_month: "",
                        spouse_dob_year: "",
                        spouse_country_of_birth: "",
                        spouse_place_of_birth: "",
                      },
                      aiExtractedData: {
                        ...(applicant.aiExtractedData || {}),
                        APPLICANT_CIVIL_STATUS: "Single",
                        PersonalData: { ...(applicant.aiExtractedData?.PersonalData || {}), marital_status: "Single" },
                        SpouseData: {
                          spouse_surname: "",
                          spouse_first_names: "",
                          spouse_surname_at_birth: "",
                          spouse_dob_day: "",
                          spouse_dob_month: "",
                          spouse_dob_year: "",
                          spouse_country_of_birth: "",
                          spouse_place_of_birth: "",
                        }
                      }
                    } : {})
                  });
                }}
                className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-cyan-300 font-bold focus:border-cyan-500 focus:outline-none"
              >
                <option value="Married">Married</option>
                <option value="Single">Single</option>
                <option value="Divorced">Divorced</option>
                <option value="Widowed">Widowed</option>
                <option value="Separated">Separated</option>
              </select>
            </div>

            {applicant.applicant_civil_status === "Married" && (
              <div className="p-4 bg-slate-900/80 rounded-xl border border-slate-800 space-y-4 mb-4">
                <h4 className="text-xs font-bold text-amber-400 uppercase tracking-wider">
                  💍 Spouse Schematics (Active for Married Applicants)
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">Surname of Spouse</label>
                    <input
                      type="text"
                      value={applicant.spouseData.spouse_surname}
                      onChange={(e) =>
                        onUpdateApplicant({
                          ...applicant,
                          spouseData: { ...applicant.spouseData, spouse_surname: e.target.value },
                        })
                      }
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">First Name(s) of Spouse</label>
                    <input
                      type="text"
                      value={applicant.spouseData.spouse_first_names}
                      onChange={(e) =>
                        onUpdateApplicant({
                          ...applicant,
                          spouseData: { ...applicant.spouseData, spouse_first_names: e.target.value },
                        })
                      }
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">Surname of Spouse at Birth</label>
                    <input
                      type="text"
                      value={applicant.spouseData.spouse_surname_at_birth}
                      onChange={(e) =>
                        onUpdateApplicant({
                          ...applicant,
                          spouseData: { ...applicant.spouseData, spouse_surname_at_birth: e.target.value },
                        })
                      }
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">Spouse DOB Day</label>
                    <input
                      type="text"
                      value={applicant.spouseData.spouse_dob_day}
                      onChange={(e) =>
                        onUpdateApplicant({
                          ...applicant,
                          spouseData: { ...applicant.spouseData, spouse_dob_day: e.target.value },
                        })
                      }
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">Spouse DOB Month</label>
                    <input
                      type="text"
                      value={applicant.spouseData.spouse_dob_month}
                      onChange={(e) =>
                        onUpdateApplicant({
                          ...applicant,
                          spouseData: { ...applicant.spouseData, spouse_dob_month: e.target.value },
                        })
                      }
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">Spouse DOB Year</label>
                    <input
                      type="text"
                      value={applicant.spouseData.spouse_dob_year}
                      onChange={(e) =>
                        onUpdateApplicant({
                          ...applicant,
                          spouseData: { ...applicant.spouseData, spouse_dob_year: e.target.value },
                        })
                      }
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">Spouse Country of Birth</label>
                    <input
                      type="text"
                      value={applicant.spouseData.spouse_country_of_birth}
                      onChange={(e) =>
                        onUpdateApplicant({
                          ...applicant,
                          spouseData: { ...applicant.spouseData, spouse_country_of_birth: e.target.value },
                        })
                      }
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">Spouse Place of Birth</label>
                    <input
                      type="text"
                      value={applicant.spouseData.spouse_place_of_birth}
                      onChange={(e) =>
                        onUpdateApplicant({
                          ...applicant,
                          spouseData: { ...applicant.spouseData, spouse_place_of_birth: e.target.value },
                        })
                      }
                      className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
                    />
                  </div>
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Father's Surname</label>
                <input
                  type="text"
                  value={applicant.familyData.father_surname}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      familyData: { ...applicant.familyData, father_surname: e.target.value },
                    })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Father's First Name</label>
                <input
                  type="text"
                  value={applicant.familyData.father_first_name}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      familyData: { ...applicant.familyData, father_first_name: e.target.value },
                    })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Mother's Surname</label>
                <input
                  type="text"
                  value={applicant.familyData.mother_surname}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      familyData: { ...applicant.familyData, mother_surname: e.target.value },
                    })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Mother's First Name</label>
                <input
                  type="text"
                  value={applicant.familyData.mother_first_name}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      familyData: { ...applicant.familyData, mother_first_name: e.target.value },
                    })
                  }
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 4: PERSONAL BIO */}
      {activeSubTab === "personal" && (
        <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800">
          <h3 className="text-xs font-bold uppercase tracking-wider text-cyan-400 mb-4 flex items-center space-x-2">
            <User className="w-4 h-4" />
            <span>Personal Data of Applicant</span>
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">Surname</label>
              <input
                type="text"
                value={applicant.personalData.surname}
                onChange={(e) =>
                  onUpdateApplicant({
                    ...applicant,
                    personalData: { ...applicant.personalData, surname: e.target.value },
                  })
                }
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">First Name(s)</label>
              <input
                type="text"
                value={applicant.personalData.first_names}
                onChange={(e) =>
                  onUpdateApplicant({
                    ...applicant,
                    personalData: { ...applicant.personalData, first_names: e.target.value },
                  })
                }
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">Sex</label>
              <select
                value={applicant.personalData.sex}
                onChange={(e) =>
                  onUpdateApplicant({
                    ...applicant,
                    personalData: { ...applicant.personalData, sex: e.target.value as any },
                  })
                }
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
              >
                <option value="Male">Male</option>
                <option value="Female">Female</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">Date of Birth (Day)</label>
              <input
                type="text"
                value={applicant.personalData.dob_day}
                onChange={(e) =>
                  onUpdateApplicant({
                    ...applicant,
                    personalData: { ...applicant.personalData, dob_day: e.target.value },
                  })
                }
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">Date of Birth (Month)</label>
              <input
                type="text"
                value={applicant.personalData.dob_month}
                onChange={(e) =>
                  onUpdateApplicant({
                    ...applicant,
                    personalData: { ...applicant.personalData, dob_month: e.target.value },
                  })
                }
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">Date of Birth (Year)</label>
              <input
                type="text"
                value={applicant.personalData.dob_year}
                onChange={(e) =>
                  onUpdateApplicant({
                    ...applicant,
                    personalData: { ...applicant.personalData, dob_year: e.target.value },
                  })
                }
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">Country of Birth</label>
              <input
                type="text"
                value={applicant.personalData.country_of_birth}
                onChange={(e) =>
                  onUpdateApplicant({
                    ...applicant,
                    personalData: { ...applicant.personalData, country_of_birth: e.target.value },
                  })
                }
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">Place of Birth</label>
              <input
                type="text"
                value={applicant.personalData.place_of_birth}
                onChange={(e) =>
                  onUpdateApplicant({
                    ...applicant,
                    personalData: { ...applicant.personalData, place_of_birth: e.target.value },
                  })
                }
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">Phone Number</label>
              <input
                type="text"
                value={applicant.personalData.phone_number}
                onChange={(e) =>
                  onUpdateApplicant({
                    ...applicant,
                    personalData: { ...applicant.personalData, phone_number: e.target.value },
                  })
                }
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
              />
            </div>
          </div>
        </div>
      )}

      {/* SECTION 5: PASSPORT & JOB */}
      {activeSubTab === "passport" && (
        <div className="bg-slate-950/60 p-5 rounded-xl border border-slate-800 space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-slate-800/80 pb-3 gap-2">
            <h3 className="text-xs font-bold uppercase tracking-wider text-cyan-400 flex items-center space-x-2">
              <FileText className="w-4 h-4" />
              <span>Travel Document & Current Occupation (10-Point Standard)</span>
            </h3>
            <div className="flex items-center space-x-2">
              <span className="text-[10px] bg-cyan-950/80 text-cyan-300 border border-cyan-800/60 px-2.5 py-1 rounded-full font-mono">
                Stage: Travel Document & Occupation
              </span>
              <span className="text-[10px] bg-emerald-950/80 text-emerald-300 border border-emerald-800/60 px-2 py-0.5 rounded font-mono">
                Format: MM/DD/YYYY
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* 01. Type of Travel Document */}
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">
                01. Type of Travel Document <span className="text-amber-400 text-[10px] ml-1">(ID: 16 - Ordinary/National passport)</span>
              </label>
              <input
                type="text"
                disabled
                value={applicant.travelDoc.travel_document_type || "Ordinary/National passport"}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-400 font-mono cursor-not-allowed select-none opacity-80"
              />
            </div>

            {/* 02. Passport Number */}
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1 flex items-center justify-between">
                <span>02. Travel Document No (Passport No)</span>
                <span className="text-[10px] text-cyan-400 font-mono">#NumarDocument</span>
              </label>
              <input
                type="text"
                value={applicant.travelDoc.passport_number}
                onChange={(e) =>
                  onUpdateApplicant({
                    ...applicant,
                    travelDoc: { ...applicant.travelDoc, passport_number: e.target.value.toUpperCase() },
                  })
                }
                placeholder="e.g. N1234567"
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
              />
            </div>

            {/* 03. Issuing Country */}
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1 flex items-center justify-between">
                <span>03. Issuing Country</span>
                <span className="text-[10px] text-cyan-400 font-mono">#TaraEmitenta (ID: 172)</span>
              </label>
              <input
                type="text"
                value={applicant.travelDoc.issuing_country || "Sri Lanka"}
                onChange={(e) =>
                  onUpdateApplicant({
                    ...applicant,
                    travelDoc: { ...applicant.travelDoc, issuing_country: e.target.value },
                  })
                }
                placeholder="Sri Lanka"
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
              />
            </div>

            {/* 04. Issuing Authority */}
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1 flex items-center justify-between">
                <span>04. Issuing Authority</span>
                <span className="text-[10px] text-slate-400 font-mono">#AutoritateEmitenta</span>
              </label>
              <input
                type="text"
                value={applicant.travelDoc.issuing_authority || "Colombo"}
                onChange={(e) =>
                  onUpdateApplicant({
                    ...applicant,
                    travelDoc: { ...applicant.travelDoc, issuing_authority: e.target.value },
                  })
                }
                placeholder="Colombo"
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
              />
            </div>

            {/* 05. Date of Issue (MM/DD/YYYY) */}
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1 flex items-center justify-between">
                <span>05. Date of Issue</span>
                <span className="text-[10px] text-emerald-400 font-mono font-bold">MM/DD/YYYY format</span>
              </label>
              <div className="space-y-1.5">
                <input
                  type="date"
                  value={fromMMDDYYYYtoInputDate(applicant.travelDoc.date_of_issue)}
                  onChange={(e) => {
                    const val = e.target.value;
                    const formatted = toMMDDYYYY(val);
                    onUpdateApplicant({
                      ...applicant,
                      travelDoc: { ...applicant.travelDoc, date_of_issue: formatted },
                    });
                  }}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                />
                <div className="flex items-center justify-between text-[10px] px-1 text-slate-400">
                  <span>Target Value:</span>
                  <span className="font-mono text-emerald-300 font-semibold bg-slate-900 px-1.5 py-0.5 rounded border border-slate-800">
                    {toMMDDYYYY(applicant.travelDoc.date_of_issue) || "MM/DD/YYYY"}
                  </span>
                </div>
              </div>
            </div>

            {/* 05b. Valid Until (MM/DD/YYYY) */}
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1 flex items-center justify-between">
                <span>05b. Valid Until (Expiry Date)</span>
                <span className="text-[10px] text-emerald-400 font-mono font-bold">MM/DD/YYYY format</span>
              </label>
              <div className="space-y-1.5">
                <input
                  type="date"
                  value={fromMMDDYYYYtoInputDate(applicant.travelDoc.valid_until)}
                  onChange={(e) => {
                    const val = e.target.value;
                    const formatted = toMMDDYYYY(val);
                    onUpdateApplicant({
                      ...applicant,
                      travelDoc: { ...applicant.travelDoc, valid_until: formatted },
                    });
                  }}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                />
                <div className="flex items-center justify-between text-[10px] px-1 text-slate-400">
                  <span>Target Value:</span>
                  <span className="font-mono text-emerald-300 font-semibold bg-slate-900 px-1.5 py-0.5 rounded border border-slate-800">
                    {toMMDDYYYY(applicant.travelDoc.valid_until) || "MM/DD/YYYY"}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* 06. Residence Permission Return */}
          <div className="bg-slate-900/60 p-3.5 rounded-lg border border-slate-800 space-y-2">
            <label className="block text-xs font-semibold text-slate-200">
              06. If you reside in a country other than your country of origin, do you have permission to return to that country?
              <span className="text-rose-400 font-bold ml-1">(Rule: Must click "No" / Not Applicable)</span>
            </label>
            <div className="flex flex-wrap items-center gap-4 text-xs">
              <label className="flex items-center space-x-2 cursor-pointer bg-slate-950 px-3 py-1.5 rounded border border-rose-900/50 text-rose-300 font-semibold">
                <input
                  type="radio"
                  name="residence_permission_return"
                  value="No"
                  checked={applicant.travelDoc.residence_permission_return === "2" || applicant.travelDoc.residence_permission_return === "No" || !applicant.travelDoc.residence_permission_return}
                  onChange={() =>
                    onUpdateApplicant({
                      ...applicant,
                      travelDoc: { ...applicant.travelDoc, residence_permission_return: "2" },
                    })
                  }
                  className="text-rose-500 focus:ring-rose-500"
                />
                <span>No (Standard Option - Enforced)</span>
              </label>

              <label className="flex items-center space-x-2 cursor-pointer text-slate-400">
                <input
                  type="radio"
                  name="residence_permission_return"
                  value="Residence is the same with the country of origin"
                  checked={applicant.travelDoc.residence_permission_return === "3" || applicant.travelDoc.residence_permission_return === "Residence is the same with the country of origin"}
                  onChange={() =>
                    onUpdateApplicant({
                      ...applicant,
                      travelDoc: { ...applicant.travelDoc, residence_permission_return: "3" },
                    })
                  }
                />
                <span>Residence is the same with country of origin (Option 3)</span>
              </label>

              <label className="flex items-center space-x-2 cursor-pointer text-slate-400">
                <input
                  type="radio"
                  name="residence_permission_return"
                  value="Yes"
                  checked={applicant.travelDoc.residence_permission_return === "1" || applicant.travelDoc.residence_permission_return === "Yes"}
                  onChange={() =>
                    onUpdateApplicant({
                      ...applicant,
                      travelDoc: { ...applicant.travelDoc, residence_permission_return: "1" },
                    })
                  }
                />
                <span>Yes (Option 1)</span>
              </label>
            </div>
          </div>

          {/* OCCUPATION SECTION WITH PRIMARY DROPDOWN & CONDITIONAL OTHER SUB-DROPDOWN */}
          <div className="bg-slate-900/80 p-4 rounded-xl border border-amber-500/30 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-amber-400 flex items-center space-x-2">
                <Briefcase className="w-4 h-4" />
                <span>07. Current Occupation & Automation Mapping</span>
              </h4>
              <span className="text-[10px] bg-amber-500/10 text-amber-300 border border-amber-500/30 px-2 py-0.5 rounded font-mono">
                Active ID: {applicant.travelDoc.occupation_id || (applicant.travelDoc.current_occupation === "Other" || !applicant.travelDoc.occupation_id ? "1" : "1")}
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Main Occupation Dropdown with IDs */}
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Occupation Selector <span className="text-amber-400 font-mono text-[10px] ml-1">(Official eVisa ID List)</span>
                </label>
                <select
                  value={applicant.travelDoc.occupation_id || (applicant.travelDoc.current_occupation === "Other" ? "1" : "1")}
                  onChange={(e) => {
                    const selectedId = e.target.value;
                    const occ = EVISA_DEFAULT_OCCUPATIONS.find((o) => o.id === selectedId);
                    onUpdateApplicant({
                      ...applicant,
                      travelDoc: {
                        ...applicant.travelDoc,
                        occupation_id: selectedId,
                        current_occupation: occ ? occ.code : "Other",
                      },
                    });
                  }}
                  className="w-full bg-slate-950 border border-amber-500/60 rounded-lg px-3 py-2.5 text-xs text-amber-300 font-semibold focus:border-amber-400 focus:outline-none"
                >
                  {EVISA_DEFAULT_OCCUPATIONS.map((occ) => (
                    <option key={occ.id} value={occ.id}>
                      {occ.label}
                    </option>
                  ))}
                </select>
                <p className="text-[10px] text-slate-400 mt-1">
                  Controls <code className="text-amber-300 font-mono">#Ocupatie_Description</code> and <code className="text-amber-300 font-mono">#Ocupatie_Id</code> in the automation script.
                </p>
              </div>

              {/* Sub-dropdown when Other (ID: 1) is chosen */}
              {(applicant.travelDoc.occupation_id === "1" || !applicant.travelDoc.occupation_id || applicant.travelDoc.current_occupation === "Other") ? (
                <div>
                  <label className="block text-xs font-semibold text-amber-300 mb-1 flex items-center justify-between">
                    <span>Other Occupation Preset</span>
                    <span className="text-[10px] text-amber-400 font-mono font-bold">Sub-dropdown</span>
                  </label>
                  <select
                    value={
                      OTHER_OCCUPATION_PRESETS.includes(applicant.travelDoc.other_occupation || "")
                        ? applicant.travelDoc.other_occupation
                        : "CUSTOM"
                    }
                    onChange={(e) => {
                      const val = e.target.value;
                      if (val !== "CUSTOM") {
                        onUpdateApplicant({
                          ...applicant,
                          travelDoc: { ...applicant.travelDoc, other_occupation: val },
                        });
                      }
                    }}
                    className="w-full bg-slate-950 border border-amber-500 rounded-lg px-3 py-2.5 text-xs text-amber-200 font-bold focus:border-amber-400 focus:outline-none"
                  >
                    {OTHER_OCCUPATION_PRESETS.map((preset) => (
                      <option key={preset} value={preset}>
                        {preset}
                      </option>
                    ))}
                    <option value="CUSTOM">-- Custom Title (Type Below) --</option>
                  </select>
                  <p className="text-[10px] text-amber-400/80 mt-1">
                    Quick-select presets: FACTORY HELPER, PACKING HELPER, HANDLER, WAREHOUSE WORKER.
                  </p>
                </div>
              ) : (
                <div>
                  <label className="block text-xs font-semibold text-slate-500 mb-1">
                    Other Occupation Sub-Dropdown
                  </label>
                  <div className="w-full bg-slate-950/60 border border-slate-800 rounded-lg px-3 py-2.5 text-xs text-slate-500 italic">
                    Disabled (Selected occupation is not "Other / ID: 1")
                  </div>
                </div>
              )}

              {/* Other Occupation Field (#AltaOcupatie) */}
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1 flex items-center justify-between">
                  <span>07b. Other Occupation Value</span>
                  <span className="text-amber-400 text-[10px] font-bold">#AltaOcupatie</span>
                </label>
                <input
                  type="text"
                  value={applicant.travelDoc.other_occupation || ""}
                  disabled={applicant.travelDoc.occupation_id !== "1" && applicant.travelDoc.occupation_id !== undefined && applicant.travelDoc.current_occupation !== "Other"}
                  onChange={(e) =>
                    onUpdateApplicant({
                      ...applicant,
                      travelDoc: { ...applicant.travelDoc, other_occupation: e.target.value.toUpperCase() },
                    })
                  }
                  placeholder="e.g. FACTORY HELPER, HANDLER"
                  className={`w-full bg-slate-900 border rounded-lg px-3 py-2 text-xs font-mono focus:outline-none transition-colors ${
                    applicant.travelDoc.occupation_id === "1" || !applicant.travelDoc.occupation_id || applicant.travelDoc.current_occupation === "Other"
                      ? "border-amber-500 text-amber-200 focus:border-amber-400 bg-slate-950 shadow-inner"
                      : "border-slate-800 text-slate-500 bg-slate-950/60 cursor-not-allowed"
                  }`}
                />
                <p className="text-[10px] text-slate-400 mt-1">
                  {applicant.travelDoc.occupation_id === "1" || !applicant.travelDoc.occupation_id || applicant.travelDoc.current_occupation === "Other"
                    ? "Injected into #AltaOcupatie on the Romanian eVisa portal."
                    : "Active only when 'Other / Alte ocupații' (ID: 1) is selected."}
                </p>
              </div>
            </div>
          </div>

          {/* 08. Employer / Education Institution (Leave Empty Rule) */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">
                08. Employer / Education Institution <span className="text-rose-400 text-[10px] font-bold ml-1">(Rule: Must Leave Empty)</span>
              </label>
              <input
                type="text"
                disabled
                value={applicant.travelDoc.employer_name || ""}
                onChange={(e) =>
                  onUpdateApplicant({
                    ...applicant,
                    travelDoc: { ...applicant.travelDoc, employer_name: "" },
                  })
                }
                placeholder="Mandated Empty (Will not be filled)"
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-500 font-mono cursor-not-allowed opacity-80 select-none"
              />
              <p className="text-[10px] text-slate-500 mt-1">
                Kept explicitly empty during automation in compliance with portal specifications.
              </p>
            </div>

            {/* 09 & 10. Photo & OpenCV Calibration Settings */}
            <div className="bg-slate-900/60 p-4 rounded-xl border border-cyan-500/30 flex flex-col justify-center gap-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-bold text-cyan-300 flex items-center space-x-1.5">
                  <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
                  <span>09. OpenCV Photo Recognition & Green Frame Calibration</span>
                </span>
                <span className="text-[10px] bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 px-2 py-0.5 rounded font-mono font-bold">
                  OpenCV Haar Cascade + 3:4 Aspect Ratio
                </span>
              </div>
              <p className="text-[11px] text-slate-300 leading-relaxed">
                The automation script scans <code className="text-emerald-300 font-mono">photo.jpg</code> using OpenCV (<code className="text-cyan-300 font-mono">cv2</code>), detects facial features with Haar Cascades, resizes & compresses the image to &le;512KB, and computes precise normalized coordinates to snap the portal's green frame (<code className="text-emerald-400 font-mono">#guideline</code>) directly around the applicant's face.
              </p>
              <div className="flex items-center space-x-2 text-emerald-400 font-medium pt-1 border-t border-slate-800">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                <span className="text-[11px]">Automatic Fallback: If no photo file exists, executes safe save (<code className="font-mono text-emerald-300">#ContinuaLaSalvare = 'True'</code>).</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 6: VISA SELECTION & MISSION */}
      {activeSubTab === "selection" && (
        <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800">
          <h3 className="text-xs font-bold uppercase tracking-wider text-purple-400 mb-4 flex items-center space-x-2">
            <FileText className="w-4 h-4" />
            <span>Select Visa Type & Consular Post Selection</span>
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">Visa Category</label>
              <select
                value={applicant.selection.visa_type}
                onChange={(e) =>
                  onUpdateApplicant({
                    ...applicant,
                    selection: { ...applicant.selection, visa_type: e.target.value as any },
                  })
                }
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-cyan-300 font-bold"
              >
                <option value="Long-stay visa">Long-stay visa</option>
                <option value="Uniform visa">Uniform visa</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">Diplomatic Mission / Consular Post</label>
              <input
                type="text"
                value={applicant.selection.diplomatic_mission}
                onChange={(e) =>
                  onUpdateApplicant({
                    ...applicant,
                    selection: { ...applicant.selection, diplomatic_mission: e.target.value },
                  })
                }
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">Purpose of Stay</label>
              <select
                value={applicant.selection.visa_purpose}
                onChange={(e) =>
                  onUpdateApplicant({
                    ...applicant,
                    selection: { ...applicant.selection, visa_purpose: e.target.value },
                  })
                }
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
              >
                <option value="Employment (marked D/AM)">Employment (marked D/AM)</option>
                <option value="Economic activities (marked D/AE)">Economic activities (marked D/AE)</option>
                <option value="Professional activities (marked D/AP)">Professional activities (marked D/AP)</option>
                <option value="Commercial activities (marked D/AC)">Commercial activities (marked D/AC)</option>
                <option value="Secondment (marked D/DT)">Secondment (marked D/DT)</option>
                <option value="Studies (marked D/SD)">Studies (marked D/SD)</option>
                <option value="Family reunification (marked D/VF)">Family reunification (marked D/VF)</option>
                <option value="Other purposes (marked D/AS)">Other purposes (marked D/AS)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1">Is Travel Document Biometric?</label>
              <select
                value={applicant.selection.is_biometric}
                onChange={(e) =>
                  onUpdateApplicant({
                    ...applicant,
                    selection: { ...applicant.selection, is_biometric: e.target.value as any },
                  })
                }
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
              >
                <option value="No">No</option>
                <option value="Yes">Yes</option>
              </select>
            </div>
          </div>
        </div>
      )}

      {/* SECTION: SUPPORTING DOCUMENTS FOLDER & CDP PLAYWRIGHT INJECTION */}
      {activeSubTab === "documents_folder" && (
        <div className="space-y-6">
          <div className="bg-slate-950/70 p-5 rounded-xl border border-emerald-500/30 shadow-lg">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4 pb-3 border-b border-slate-800">
              <div className="flex items-center space-x-3">
                <div className="p-2.5 bg-emerald-500/10 text-emerald-400 rounded-xl border border-emerald-500/20">
                  <FolderOpen className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
                    <span>Local Documents Folder Configuration</span>
                    <span className="bg-emerald-500/20 text-emerald-300 text-[10px] font-mono px-2 py-0.5 rounded-full border border-emerald-500/30">
                      Playwright CDP Injection
                    </span>
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Specify the local folder on your computer. The automation script will scan this directory, match files by keyword, and inject them into the exact Kendo UI hidden inputs.
                  </p>
                </div>
              </div>

              <div className="flex items-center space-x-2">
                <span className="text-xs text-slate-400">Status:</span>
                <span className="text-xs font-semibold text-emerald-400 flex items-center space-x-1">
                  <ShieldCheck className="w-4 h-4" />
                  <span>Kendo 6-Field Map Active</span>
                </span>
              </div>
            </div>

            {/* Folder Path Input & Quick Presets */}
            <div className="space-y-3 mb-6">
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-300">
                Local Folder Path (Absolute Computer Directory):
              </label>
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                <div className="relative flex-1">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-500">
                    <HardDrive className="w-4 h-4" />
                  </div>
                  <input
                    type="text"
                    value={applicant.documentsFolderPath || "C:/VisaDocs/"}
                    onChange={(e) =>
                      onUpdateApplicant({
                        ...applicant,
                        documentsFolderPath: e.target.value,
                      })
                    }
                    placeholder="e.g. C:/VisaDocs/ or /home/user/VisaDocs/"
                    className="w-full bg-slate-900 border border-slate-700 focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 rounded-xl pl-9 pr-3 py-2.5 text-xs text-emerald-300 font-mono font-medium shadow-inner"
                  />
                </div>

                <div className="flex items-center space-x-1.5">
                  <button
                    type="button"
                    onClick={() =>
                      onUpdateApplicant({
                        ...applicant,
                        documentsFolderPath: "C:/VisaDocs/",
                      })
                    }
                    className="px-2.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] font-mono rounded-lg border border-slate-700 transition-colors"
                    title="Set to C:/VisaDocs/"
                  >
                    C:/VisaDocs/
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      onUpdateApplicant({
                        ...applicant,
                        documentsFolderPath: "C:/docs/",
                      })
                    }
                    className="px-2.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] font-mono rounded-lg border border-slate-700 transition-colors"
                    title="Set to C:/docs/"
                  >
                    C:/docs/
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      onUpdateApplicant({
                        ...applicant,
                        documentsFolderPath: "./documents/",
                      })
                    }
                    className="px-2.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] font-mono rounded-lg border border-slate-700 transition-colors"
                    title="Set to ./documents/"
                  >
                    ./documents/
                  </button>
                </div>
              </div>
              <p className="text-[11px] text-slate-500">
                Tip: Use forward slashes <code className="text-slate-400">/</code> or escaped backslashes <code className="text-slate-400">\\</code>. The script uses direct browser debugging commands to attach files without needing to open OS file explorer dialogs.
              </p>
            </div>

            {/* 6-Field Explicit Kendo UI Input Mapping Table */}
            <div className="space-y-3">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center justify-between">
                <span>Verified E-Visa Upload Elements &amp; Keyword Matchers:</span>
                <span className="text-[11px] font-normal text-slate-400">
                  Target Endpoint: <code className="text-emerald-400">/Vize/SalveazaDocumentPeDocumentJustificativ</code>
                </span>
              </h4>

              <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800 font-mono text-[11px]">
                    <tr>
                      <th className="py-2.5 px-3">#</th>
                      <th className="py-2.5 px-3">Document Category</th>
                      <th className="py-2.5 px-3">Exact Hidden Input ID</th>
                      <th className="py-2.5 px-3">Filename Keyword</th>
                      <th className="py-2.5 px-3">File Formats &amp; Max Size</th>
                      <th className="py-2.5 px-3">Error DOM Element</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                    <tr className="hover:bg-slate-800/30">
                      <td className="py-2.5 px-3 text-cyan-400 font-bold">1</td>
                      <td className="py-2.5 px-3 font-sans text-slate-200 font-semibold">WORK PERMIT</td>
                      <td className="py-2.5 px-3 text-emerald-400 font-bold">#UploadDocumenteJustificative_30</td>
                      <td className="py-2.5 px-3"><span className="px-2 py-0.5 bg-emerald-500/10 text-emerald-300 rounded border border-emerald-500/20">permit</span></td>
                      <td className="py-2.5 px-3 text-slate-400">.pdf, .jpg, .png (≤ 2MB)</td>
                      <td className="py-2.5 px-3 text-slate-500">#UploadDocumenteJustificative_30_TextEroare</td>
                    </tr>
                    <tr className="hover:bg-slate-800/30">
                      <td className="py-2.5 px-3 text-cyan-400 font-bold">2</td>
                      <td className="py-2.5 px-3 font-sans text-slate-200 font-semibold">MEANS OF SUPPORT</td>
                      <td className="py-2.5 px-3 text-emerald-400 font-bold">#UploadDocumenteJustificative_31</td>
                      <td className="py-2.5 px-3"><span className="px-2 py-0.5 bg-emerald-500/10 text-emerald-300 rounded border border-emerald-500/20">support</span></td>
                      <td className="py-2.5 px-3 text-slate-400">.pdf, .jpg, .png (≤ 2MB)</td>
                      <td className="py-2.5 px-3 text-slate-500">#UploadDocumenteJustificative_31_TextEroare</td>
                    </tr>
                    <tr className="hover:bg-slate-800/30">
                      <td className="py-2.5 px-3 text-cyan-400 font-bold">3</td>
                      <td className="py-2.5 px-3 font-sans text-slate-200 font-semibold">CRIMINAL RECORD</td>
                      <td className="py-2.5 px-3 text-emerald-400 font-bold">#UploadDocumenteJustificative_32</td>
                      <td className="py-2.5 px-3"><span className="px-2 py-0.5 bg-emerald-500/10 text-emerald-300 rounded border border-emerald-500/20">criminal</span></td>
                      <td className="py-2.5 px-3 text-slate-400">.pdf, .jpg, .png (≤ 2MB)</td>
                      <td className="py-2.5 px-3 text-slate-500">#UploadDocumenteJustificative_32_TextEroare</td>
                    </tr>
                    <tr className="hover:bg-slate-800/30">
                      <td className="py-2.5 px-3 text-cyan-400 font-bold">4</td>
                      <td className="py-2.5 px-3 font-sans text-slate-200 font-semibold">TRAVEL MEDICAL INSURANCE</td>
                      <td className="py-2.5 px-3 text-emerald-400 font-bold">#UploadDocumenteJustificative_10</td>
                      <td className="py-2.5 px-3"><span className="px-2 py-0.5 bg-emerald-500/10 text-emerald-300 rounded border border-emerald-500/20">insurance</span></td>
                      <td className="py-2.5 px-3 text-slate-400">.pdf, .jpg, .png (≤ 2MB)</td>
                      <td className="py-2.5 px-3 text-slate-500">#UploadDocumenteJustificative_10_TextEroare</td>
                    </tr>
                    <tr className="hover:bg-slate-800/30">
                      <td className="py-2.5 px-3 text-cyan-400 font-bold">5</td>
                      <td className="py-2.5 px-3 font-sans text-slate-200 font-semibold">VALID TRAVEL DOCUMENT</td>
                      <td className="py-2.5 px-3 text-emerald-400 font-bold">#UploadDocumenteJustificative_1</td>
                      <td className="py-2.5 px-3"><span className="px-2 py-0.5 bg-emerald-500/10 text-emerald-300 rounded border border-emerald-500/20">passport</span></td>
                      <td className="py-2.5 px-3 text-slate-400">.pdf, .jpg, .png (≤ 2MB)</td>
                      <td className="py-2.5 px-3 text-slate-500">#UploadDocumenteJustificative_1_TextEroare</td>
                    </tr>
                    <tr className="hover:bg-slate-800/30">
                      <td className="py-2.5 px-3 text-cyan-400 font-bold">6</td>
                      <td className="py-2.5 px-3 font-sans text-slate-200 font-semibold">PHOTOGRAPHS</td>
                      <td className="py-2.5 px-3 text-emerald-400 font-bold">#UploadDocumenteJustificative_2</td>
                      <td className="py-2.5 px-3"><span className="px-2 py-0.5 bg-emerald-500/10 text-emerald-300 rounded border border-emerald-500/20">photo</span></td>
                      <td className="py-2.5 px-3 text-slate-400">.jpg, .jpeg, .png (≤ 2MB)</td>
                      <td className="py-2.5 px-3 text-slate-500">#UploadDocumenteJustificative_2_TextEroare</td>
                    </tr>
                    <tr className="hover:bg-slate-800/30">
                      <td className="py-2.5 px-3 text-slate-500 font-bold">+</td>
                      <td className="py-2.5 px-3 font-sans text-slate-300">OTHER SUPPORTING FILES</td>
                      <td className="py-2.5 px-3 text-slate-400">#UploadotherFiles</td>
                      <td className="py-2.5 px-3"><span className="px-2 py-0.5 bg-slate-800 text-slate-400 rounded">optional</span></td>
                      <td className="py-2.5 px-3 text-slate-400">.pdf, .jpg (≤ 2MB)</td>
                      <td className="py-2.5 px-3 text-slate-500">#UploadotherFiles_TextEroare</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Technical Verification & Preservation Rules */}
            <div className="mt-5 grid grid-cols-1 md:grid-cols-3 gap-3 pt-4 border-t border-slate-800/80">
              <div className="bg-slate-900/80 p-3 rounded-lg border border-slate-800">
                <div className="flex items-center space-x-2 text-cyan-400 text-xs font-bold mb-1">
                  <FileUp className="w-4 h-4" />
                  <span>Kendo autoUpload: true</span>
                </div>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  Setting the file path triggers Kendo's async AJAX POST to <span className="text-slate-300 font-mono">SalveazaDocumentPeDocumentJustificativ</span>. The automation script waits for HTTP 200 before proceeding to the next field.
                </p>
              </div>

              <div className="bg-slate-900/80 p-3 rounded-lg border border-slate-800">
                <div className="flex items-center space-x-2 text-amber-400 text-xs font-bold mb-1">
                  <AlertTriangle className="w-4 h-4" />
                  <span>Session Expiry Guard</span>
                </div>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  Automatically checks for <span className="text-amber-300 font-semibold">"Sesiunea a expirat"</span>. If detected, performs 1-2 automatic page refreshes to recover the active session without losing progress.
                </p>
              </div>

              <div className="bg-slate-900/80 p-3 rounded-lg border border-slate-800">
                <div className="flex items-center space-x-2 text-emerald-400 text-xs font-bold mb-1">
                  <ShieldCheck className="w-4 h-4" />
                  <span>Remaining Flow Preserved</span>
                </div>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  After all files finish uploading, the mandatory declaration checkbox is locked, <span className="text-emerald-300 font-semibold">Save</span> is clicked, and <span className="text-emerald-300 font-semibold">Next</span> is executed seamlessly to advance to the Summary stage.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
