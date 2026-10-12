import React, { useState, useMemo, useEffect } from "react";
import JSZip from "jszip";
import {
  Sparkles,
  Upload,
  FileText,
  Check,
  AlertCircle,
  ArrowRight,
  RefreshCw,
  Copy,
  User,
  Heart,
  Building2,
  Layers,
  FolderOpen,
  HardDrive,
  Briefcase,
  FileSpreadsheet,
  Calendar,
  Download,
  Terminal,
  ExternalLink,
  ShieldCheck,
  ShieldAlert,
  CheckCircle,
  XCircle,
  AlertTriangle,
  FileCheck,
  Filter,
  Search,
  Info,
  Lock,
  Eye,
  X,
  Package,
  CheckCircle2,
  Globe,
  MapPin,
  PhoneCall
} from "lucide-react";
import { ApplicantRecord } from "../types";
import { EVISA_DEFAULT_OCCUPATIONS } from "./ApplicantSchematicsEditor";
import { calculateJourneyAndInsuranceDates } from "../utils/dateCalculations";
import {
  validateExtractedData,
  ValidationSummary,
  FieldValidationResult
} from "../utils/documentValidation";

// Helper function to normalize Father's Surname and First Name
// Rule: If father's surname is an initial or contains initials in the applicant's application/documents,
// add applicant's extracted surname into the Father Surname field,
// and move any other names or initials into the Father First Name field.
export function normalizeFamilyFatherData(familyData: any, applicantSurname: string) {
  if (!familyData) return familyData;
  const appSur = String(applicantSurname || "").trim();
  if (!appSur) return familyData;

  let fSur = String(familyData.father_surname || familyData.fatherSurname || "").trim();
  let fFirst = String(familyData.father_first_name || familyData.fatherFirstName || "").trim();

  const isInitialToken = (t: string) => {
    const clean = t.replace(/\./g, "").trim();
    return clean.length > 0 && clean.length <= 2 && /^[A-Za-z]+$/.test(clean);
  };

  const tokens = fSur.split(/\s+/).filter(Boolean);
  const hasInitial = tokens.some(t => isInitialToken(t));
  const isSurInitial = tokens.length > 0 && tokens.every(t => isInitialToken(t));
  const cleanFSur = fSur.replace(/[^A-Za-z]/g, "").toUpperCase();
  const cleanAppSur = appSur.replace(/[^A-Za-z]/g, "").toUpperCase();

  // Trigger if father_surname is an initial, contains initials, or clean length <= 2
  if (hasInitial || isSurInitial || cleanFSur.length <= 2) {
    const otherNames: string[] = [];

    for (const token of tokens) {
      const cleanToken = token.replace(/[^A-Za-z]/g, "").toUpperCase();
      if (!cleanToken) continue;
      // If this token matches the full applicant surname, don't move to other names
      if (cleanToken === cleanAppSur) {
        continue;
      }
      // If it's an initial that directly matches the first letter of applicant surname (e.g. 'P' or 'P.' for 'PERERA')
      if (isInitialToken(token) && cleanAppSur && cleanToken === cleanAppSur.charAt(0)) {
        continue;
      }
      otherNames.push(token);
    }

    // Set ONLY the correct surname into Father Surname
    familyData.father_surname = appSur.toUpperCase();
    if (familyData.fatherSurname) familyData.fatherSurname = appSur.toUpperCase();

    // Move any other names or initials into Father First Name
    if (otherNames.length > 0) {
      const existingTokens = fFirst.split(/\s+/).map(w => w.replace(/[^A-Za-z]/g, "").toUpperCase()).filter(Boolean);
      const toAdd = otherNames.filter(w => !existingTokens.includes(w.replace(/[^A-Za-z]/g, "").toUpperCase()));
      if (toAdd.length > 0) {
        familyData.father_first_name = [toAdd.join(" "), fFirst].filter(Boolean).join(" ").trim().toUpperCase();
        if (familyData.fatherFirstName) familyData.fatherFirstName = familyData.father_first_name;
      }
    }
  }

  return familyData;
}

interface AiDocumentExtractorProps {
  applicant: ApplicantRecord;
  onUpdateApplicant: (updated: ApplicantRecord) => void;
}

type ExtractionCategory = "applicant" | "spouse" | "company" | "other";

const initialSampleDates = calculateJourneyAndInsuranceDates();

const SAMPLE_DATA: Record<ExtractionCategory, string> = {
  applicant: `VISA APPLICANT SCHEMATICS (Passport, Work Permit & Police Clearance):
Applicant Name: PERERA ANUSHKA DILHANI
Surname: PERERA
First Names: ANUSHKA DILHANI
Work Permit Number (Aviz de Munca): WP-2026-991823
Father's Name: PERERA SUNIL
Father Surname: PERERA
Father First Name: SUNIL
Mother's Name: FERNANDO KANTI
Mother Surname: FERNANDO
Mother First Name: KANTI
Civil Status: Married
Date of Birth: 10/03/1997
Place of Birth: MARAWILA, Sri Lanka
Nationality: Sri Lanka
Passport Number: N8234198
Date of Issue: 2021-05-15
Valid Until: 2031-05-14
Issuing Authority: Colombo
Address: NO. 45, TEMPLE ROAD, MARAWILA, SRI LANKA
Phone Number: +94 77 123 4567`,

  spouse: `SPOUSE ID CARD / MARRIAGE CERTIFICATE DATA:
Spouse Surname: PERERA
Spouse First Name: SUNIL CHAMARA
Spouse Surname at Birth: PERERA
Spouse Date of Birth: 14/08/1994
Spouse Country of Birth: Sri Lanka
Spouse Place of Birth: COLOMBO`,

  company: `ROMANIAN COMPANY DETAILS & INVITATION:
Societatea: RETEX GREEN SRL
Cod Ocupatie: Muncitor necalificat in industria prelucratoare (COR 932904)
Job Position Translated: FACTORY HELPER
Telephone/Fax: 0040764883396
Full Address: Tirgu Lapus, str. Tiblesului, no. 112, county Maramures, Romania
Email: contact@retexgreen.ro`,

  other: `SUPPORTING DOCUMENTS & TRAVEL DETAILS:
Travel Medical Insurance Valid Until: ${initialSampleDates.insurance_valid_until}
Cost Coverage: Host company
Means of Support: Cash, Accommodation, Insurance
Means of Transport: air travel
Intended Arrival: ${initialSampleDates.arrival_date}
Intended Departure: ${initialSampleDates.departure_date}`,
};

const OTHER_OCCUPATION_PRESETS = [
  "FACTORY HELPER",
  "PACKING HELPER",
  "HANDLER",
  "WAREHOUSE WORKER",
  "PRODUCTION OPERATOR",
  "CONSTRUCTION WORKER",
  "AGRICULTURAL WORKER",
  "CLEANER / HOUSEKEEPER",
];

export const AiDocumentExtractor: React.FC<AiDocumentExtractorProps> = ({
  applicant,
  onUpdateApplicant,
}) => {
  const [activeCategory, setActiveCategory] = useState<ExtractionCategory>("applicant");
  const [viewMode, setViewMode] = useState<"visual" | "json" | "validation">("visual");
  const [validationFilter, setValidationFilter] = useState<"all" | "attention" | "verified">("all");
  const [showValidationGateModal, setShowValidationGateModal] = useState<boolean>(false);
  const [pendingScriptAction, setPendingScriptAction] = useState<"apply" | "py" | "bat" | "zip" | null>(null);

  const [inputs, setInputs] = useState<Record<ExtractionCategory, string>>({
    applicant: SAMPLE_DATA.applicant,
    spouse: SAMPLE_DATA.spouse,
    company: SAMPLE_DATA.company,
    other: SAMPLE_DATA.other,
  });

  const [imageFiles, setImageFiles] = useState<
    Record<ExtractionCategory, Array<{ base64: string; mimeType: string; name: string }>>
  >({
    applicant: [],
    spouse: [],
    company: [],
    other: [],
  });

  const [isExtracting, setIsExtracting] = useState<boolean>(false);
  const [extractedResult, setExtractedResult] = useState<any | null>(applicant.aiExtractedData || null);
  const [extractError, setExtractError] = useState<string | null>(null);
  const [appliedSuccess, setAppliedSuccess] = useState<boolean>(false);
  const [isDragging, setIsDragging] = useState<boolean>(false);

  useEffect(() => {
    if (applicant.aiExtractedData) {
      setExtractedResult(applicant.aiExtractedData);
    } else {
      setExtractedResult(null);
    }
  }, [applicant.id, applicant.aiExtractedData]);

  // AI Model Selection & Quota Options
  const [selectedModel, setSelectedModel] = useState<string>("auto");
  const [lastModelUsed, setLastModelUsed] = useState<string | null>(null);
  const [usedFallbackEngine, setUsedFallbackEngine] = useState<boolean>(false);

  // Automation Script Configuration
  const [documentsFolderPath, setDocumentsFolderPath] = useState<string>(
    applicant.documentsFolderPath || "C:/VisaDocs/"
  );
  const [startUrl, setStartUrl] = useState<string>(
    applicant.verificationUrl || "https://eviza.mae.ro/home?lang=en"
  );
  const [isDownloadingScript, setIsDownloadingScript] = useState<boolean>(false);
  const [isDownloadingBat, setIsDownloadingBat] = useState<boolean>(false);
  const [isDownloadingZip, setIsDownloadingZip] = useState<boolean>(false);
  const [showCodePreview, setShowCodePreview] = useState<boolean>(false);
  const [previewCode, setPreviewCode] = useState<string>("");
  const [copiedCode, setCopiedCode] = useState<boolean>(false);

  const compressImageFile = (file: File): Promise<{ base64: string; mimeType: string; name: string }> => {
    return new Promise((resolve) => {
      if (!file.type.startsWith("image/") || file.size < 300 * 1024) {
        const reader = new FileReader();
        reader.onload = () => resolve({ base64: reader.result as string, mimeType: file.type || "image/jpeg", name: file.name });
        reader.onerror = () => resolve({ base64: "", mimeType: file.type, name: file.name });
        reader.readAsDataURL(file);
        return;
      }
      const img = new Image();
      const url = URL.createObjectURL(file);
      img.onload = () => {
        const maxDim = 1600;
        let w = img.width;
        let h = img.height;
        if (w > maxDim || h > maxDim) {
          if (w > h) {
            h = Math.round((h * maxDim) / w);
            w = maxDim;
          } else {
            w = Math.round((w * maxDim) / h);
            h = maxDim;
          }
        }
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext("2d");
        if (ctx) {
          ctx.fillStyle = "#FFFFFF";
          ctx.fillRect(0, 0, w, h);
          ctx.drawImage(img, 0, 0, w, h);
        }
        const base64 = canvas.toDataURL("image/jpeg", 0.85);
        URL.revokeObjectURL(url);
        resolve({ base64, mimeType: "image/jpeg", name: file.name });
      };
      img.onerror = () => {
        const reader = new FileReader();
        reader.onload = () => resolve({ base64: reader.result as string, mimeType: file.type || "image/jpeg", name: file.name });
        reader.readAsDataURL(file);
      };
      img.src = url;
    });
  };

  const processFiles = (category: ExtractionCategory, files: FileList | File[]) => {
    Array.from(files).forEach(async (file) => {
      const compressed = await compressImageFile(file);
      if (compressed.base64) {
        setImageFiles((prev) => ({
          ...prev,
          [category]: [
            ...prev[category],
            compressed,
          ],
        }));
      }
    });
  };

  const handleFileUpload = (category: ExtractionCategory, e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      processFiles(category, files);
    }
  };

  const handleDrop = (category: ExtractionCategory, e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      processFiles(category, files);
    }
  };

  const handleRemoveFile = (category: ExtractionCategory, index: number) => {
    setImageFiles((prev) => ({
      ...prev,
      [category]: prev[category].filter((_, i) => i !== index),
    }));
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleLoadSample = () => {
    setInputs({ ...SAMPLE_DATA });
  };

  const handleRunAiExtraction = async () => {
    setIsExtracting(true);
    setExtractError(null);
    setAppliedSuccess(false);

    try {
      const allImages = [
        ...imageFiles.applicant.map((img) => ({ ...img, category: "Applicant (Passport, Work Permit, Police Report)" })),
        ...imageFiles.spouse.map((img) => ({ ...img, category: "Spouse (Marriage Certificate, Spouse ID Card)" })),
        ...imageFiles.company.map((img) => ({ ...img, category: "Company (Romanian Employer Invitation, Aviz de Angajare, Registration)" })),
        ...imageFiles.other.map((img) => ({ ...img, category: "Other Supporting Documents (Medical Insurance, Flight Itinerary)" })),
      ];

      const allCategoriesData = {
        applicantText: inputs.applicant,
        spouseText: inputs.spouse,
        companyText: inputs.company,
        otherText: inputs.other,
      };

      const response = await fetch("/api/ai/extract-data", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          documentText: `Applicant: ${inputs.applicant}\nSpouse: ${inputs.spouse}\nCompany: ${inputs.company}\nOther: ${inputs.other}`,
          images: allImages.map((img) => ({
            base64: img.base64,
            mimeType: img.mimeType,
            name: img.name,
            category: img.category,
          })),
          allCategoriesData,
          extractionType: "simultaneous_all_sections",
          selectedModel,
        }),
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(data.error || "AI Extraction failed.");
      }

      const ext = data.extractedData || {};
      // Ensure journey dates adhere to the user's rule (Arrival = today's date of next month, Departure = 3 months from arrival)
      if (!ext.JourneyDetailsData || !ext.JourneyDetailsData.arrival_date || !ext.JourneyDetailsData.departure_date) {
        const calculatedDates = calculateJourneyAndInsuranceDates();
        if (!ext.JourneyDetailsData) ext.JourneyDetailsData = {};
        if (!ext.JourneyDetailsData.arrival_date) ext.JourneyDetailsData.arrival_date = calculatedDates.arrival_date;
        if (!ext.JourneyDetailsData.departure_date) ext.JourneyDetailsData.departure_date = calculatedDates.departure_date;
        if (!ext.CostAndMeansData) ext.CostAndMeansData = {};
        if (!ext.CostAndMeansData.insurance_valid_until) ext.CostAndMeansData.insurance_valid_until = calculatedDates.insurance_valid_until;
      }

      // Rule: If father's surname is an initial or contains initials in the applicant's application/documents,
      // add applicant's extracted surname into the Father Surname field,
      // and move any other names or initials into the Father First Name field.
      const appSur = ext.PersonalData?.surname || applicant.personalData.surname || "";
      if (ext.FamilyData && appSur) {
        normalizeFamilyFatherData(ext.FamilyData, appSur);
      }

      setExtractedResult(ext);
      setLastModelUsed(data.modelUsed || "Gemini Flash");
      setUsedFallbackEngine(!!data.usedFallback);
    } catch (err: any) {
      setExtractError(err.message || "Failed to process documents with Gemini AI.");
    } finally {
      setIsExtracting(false);
    }
  };

  const handleApplyToState = () => {
    if (!extractedResult) return;

    // Create a deeply copied object structure to strictly enforce immutability and trigger React re-renders flawlessly.
    const updated: ApplicantRecord = {
      ...applicant,
      personalData: { ...applicant.personalData },
      travelDoc: { ...applicant.travelDoc },
      addressData: { ...applicant.addressData },
      spouseData: { ...applicant.spouseData },
      familyData: { ...applicant.familyData },
      companyContactData: { ...applicant.companyContactData },
      hostData: { ...applicant.hostData },
      costAndMeansData: { ...applicant.costAndMeansData },
      journeyDetailsData: { ...applicant.journeyDetailsData },
      visaRequestedDetails: { ...applicant.visaRequestedDetails },
    };

    updated.documentsFolderPath = documentsFolderPath;
    updated.photoUploadFolderPath = documentsFolderPath;
    updated.verificationUrl = startUrl;

    if (extractedResult.APPLICANT_CIVIL_STATUS) {
      updated.applicant_civil_status = extractedResult.APPLICANT_CIVIL_STATUS;
    }
    if (extractedResult.PersonalData) {
      updated.personalData = { ...updated.personalData, ...extractedResult.PersonalData };
      if (extractedResult.PersonalData.work_permit_number) {
        updated.companyContactData.work_permit_number = extractedResult.PersonalData.work_permit_number;
      }
    }
    if (extractedResult.TravelDocument) {
      const occId = extractedResult.TravelDocument.occupation_id || updated.travelDoc.occupation_id || "1";
      const currOcc = extractedResult.TravelDocument.current_occupation || updated.travelDoc.current_occupation || "Other";
      updated.travelDoc = {
        ...updated.travelDoc,
        ...extractedResult.TravelDocument,
        current_occupation: currOcc,
        occupation_id: occId,
        other_occupation:
          extractedResult.TravelDocument.other_occupation ||
          (extractedResult.TravelDocument.current_occupation !== "Other" && extractedResult.TravelDocument.current_occupation
            ? extractedResult.TravelDocument.current_occupation
            : "FACTORY HELPER"),
      };
    }
    if (extractedResult.AddressData) {
      updated.addressData = { ...updated.addressData, ...extractedResult.AddressData };
    }
    if (extractedResult.SpouseData) {
      const spSur = extractedResult.SpouseData.spouse_surname || updated.spouseData.spouse_surname || "";
      const spFirst =
        extractedResult.SpouseData.spouse_first_names ||
        extractedResult.SpouseData.spouse_first_name ||
        (extractedResult.SpouseData as any).first_names ||
        (extractedResult.SpouseData as any).first_name ||
        updated.spouseData.spouse_first_names ||
        (updated.spouseData as any).spouse_first_name ||
        "";
      const spBirthSur =
        extractedResult.SpouseData.spouse_surname_at_birth ||
        updated.spouseData.spouse_surname_at_birth ||
        spSur;

      let spDobDay = extractedResult.SpouseData.spouse_dob_day || updated.spouseData.spouse_dob_day || "";
      let spDobMonth = extractedResult.SpouseData.spouse_dob_month || updated.spouseData.spouse_dob_month || "";
      let spDobYear = extractedResult.SpouseData.spouse_dob_year || updated.spouseData.spouse_dob_year || "";
      const rawDob =
        extractedResult.SpouseData.spouse_dob ||
        (extractedResult.SpouseData as any).dob ||
        (extractedResult.SpouseData as any).spouse_birth_date ||
        "";
      if (rawDob && (!spDobDay || !spDobYear)) {
        const parts = String(rawDob).split(/[\/\-\.]/);
        if (parts.length === 3) {
          if (parts[0].length === 4) {
            spDobYear = parts[0];
            spDobMonth = parts[1];
            spDobDay = parts[2];
          } else {
            spDobDay = parts[0];
            spDobMonth = parts[1];
            spDobYear = parts[2];
          }
        }
      }

      updated.spouseData = {
        ...updated.spouseData,
        ...extractedResult.SpouseData,
        spouse_surname: spSur,
        spouse_first_names: spFirst,
        spouse_surname_at_birth: spBirthSur,
        spouse_dob_day: spDobDay,
        spouse_dob_month: spDobMonth,
        spouse_dob_year: spDobYear,
        spouse_country_of_birth: extractedResult.SpouseData.spouse_country_of_birth || updated.spouseData.spouse_country_of_birth || "Sri Lanka",
        spouse_place_of_birth: extractedResult.SpouseData.spouse_place_of_birth || updated.spouseData.spouse_place_of_birth || "COLOMBO",
      };
      (updated.spouseData as any).spouse_first_name = spFirst;

      const rawCivilStatus = String(
        extractedResult.APPLICANT_CIVIL_STATUS ||
        extractedResult.PersonalData?.marital_status ||
        updated.applicant_civil_status ||
        updated.personalData.marital_status ||
        ""
      ).trim().toLowerCase();

      const isExplicitSingle = rawCivilStatus.includes("singl") || rawCivilStatus.includes("celibat") || rawCivilStatus.includes("necasat") || rawCivilStatus.includes("necăsăt") || rawCivilStatus.includes("unmarr") || rawCivilStatus === "1";
      const isExplicitMarried = (rawCivilStatus.includes("marr") || rawCivilStatus.includes("casat") || rawCivilStatus.includes("căsăt") || rawCivilStatus === "2") && !isExplicitSingle;

      if (isExplicitSingle) {
        updated.applicant_civil_status = "Single";
        updated.personalData.marital_status = "Single";
        updated.spouseData = {
          spouse_surname: "",
          spouse_first_names: "",
          spouse_surname_at_birth: "",
          spouse_dob_day: "",
          spouse_dob_month: "",
          spouse_dob_year: "",
          spouse_country_of_birth: "",
          spouse_place_of_birth: "",
        };
        (updated.spouseData as any).spouse_first_name = "";
      } else if (isExplicitMarried || (Boolean(extractedResult.SpouseData?.spouse_surname || extractedResult.SpouseData?.spouse_first_names) && !isExplicitSingle)) {
        updated.applicant_civil_status = "Married";
        updated.personalData.marital_status = "Married";
      }
    }
    if (extractedResult.FamilyData) {
      const appSur = extractedResult.PersonalData?.surname || applicant.personalData.surname || "";
      const famCopy = { ...extractedResult.FamilyData };
      if (appSur) {
        normalizeFamilyFatherData(famCopy, appSur);
      }
      updated.familyData = { ...updated.familyData, ...famCopy };
    }
    if (extractedResult.CompanyContactData) {
      const comp = extractedResult.CompanyContactData;
      const compName = comp.name || comp.company_name || comp.employer_name || "";
      const compAddr = comp.full_address || comp.address || comp.company_address || "";
      const compPhone = comp.telephone_fax || comp.phone || comp.company_phone || "";
      const compEmail = comp.email || comp.company_email || "";
      const compWp = comp.work_permit_number || "";

      updated.companyContactData = {
        ...updated.companyContactData,
        ...comp,
        name: compName || updated.companyContactData.name,
        full_address: compAddr || updated.companyContactData.full_address,
        telephone_fax: compPhone || updated.companyContactData.telephone_fax,
        email: compEmail || updated.companyContactData.email,
        work_permit_number: compWp || updated.companyContactData.work_permit_number,
      };
      if (compWp) {
        updated.personalData.work_permit_number = compWp;
      }
      if (compName) {
        updated.hostData.hotel_name = compName;
        updated.costAndMeansData.host_name = compName;
      }
      if (compAddr) {
        updated.hostData.host_address = compAddr;
      }
      if (compEmail) {
        updated.hostData.host_email = compEmail;
        updated.hostData.email = compEmail;
      }
      if (compPhone) {
        updated.hostData.host_phone = compPhone;
      }
    }
    if (extractedResult.HostData) {
      updated.hostData = {
        ...updated.hostData,
        ...extractedResult.HostData,
        type_of_host: extractedResult.HostData.type_of_host || updated.hostData.type_of_host || "Company",
        hotel_name: extractedResult.HostData.hotel_name || updated.hostData.hotel_name || updated.companyContactData.name,
        host_address: extractedResult.HostData.host_address || updated.hostData.host_address || updated.companyContactData.full_address,
      };
      if (extractedResult.HostData.hotel_name) {
        updated.costAndMeansData.host_name = extractedResult.HostData.hotel_name;
      }
    }
    if (extractedResult.CostAndMeansData) {
      updated.costAndMeansData = {
        ...updated.costAndMeansData,
        ...extractedResult.CostAndMeansData,
        cost_covered_by: "Host company",
        means_cash: true,
        means_accommodation: true,
        means_insurance: true,
      };
    }
    if (extractedResult.JourneyDetailsData) {
      updated.journeyDetailsData = {
        ...updated.journeyDetailsData,
        ...extractedResult.JourneyDetailsData,
      };
    }
    if (extractedResult.VisaRequestedDetails) {
      updated.visaRequestedDetails = {
        ...updated.visaRequestedDetails,
        ...extractedResult.VisaRequestedDetails,
        means_of_transport: "air travel",
      };
    }

    updated.aiExtractedData = extractedResult;
    onUpdateApplicant(updated);
    setAppliedSuccess(true);
    setTimeout(() => setAppliedSuccess(false), 3000);
  };

  const getEffectiveApplicant = (): ApplicantRecord => {
    // Return a deeply copied object structure to ensure no raw properties are mutated during processing.
    const eff: ApplicantRecord = {
      ...applicant,
      personalData: { ...applicant.personalData },
      travelDoc: { ...applicant.travelDoc },
      addressData: { ...applicant.addressData },
      spouseData: { ...applicant.spouseData },
      familyData: { ...applicant.familyData },
      companyContactData: { ...applicant.companyContactData },
      hostData: { ...applicant.hostData },
      costAndMeansData: { ...applicant.costAndMeansData },
      journeyDetailsData: { ...applicant.journeyDetailsData },
      visaRequestedDetails: { ...applicant.visaRequestedDetails },
    };

    eff.documentsFolderPath = documentsFolderPath;
    eff.photoUploadFolderPath = documentsFolderPath;
    eff.verificationUrl = startUrl;

    if (extractedResult) {
      eff.aiExtractedData = extractedResult;
      if (extractedResult.APPLICANT_CIVIL_STATUS) eff.applicant_civil_status = extractedResult.APPLICANT_CIVIL_STATUS;
      if (extractedResult.PersonalData) {
        eff.personalData = { ...eff.personalData, ...extractedResult.PersonalData };
        if (extractedResult.PersonalData.work_permit_number) {
          eff.companyContactData.work_permit_number = extractedResult.PersonalData.work_permit_number;
        }
      }
      if (extractedResult.TravelDocument) {
        eff.travelDoc = {
          ...eff.travelDoc,
          ...extractedResult.TravelDocument,
          other_occupation: extractedResult.TravelDocument.other_occupation || "FACTORY HELPER",
        };
      }
      if (extractedResult.AddressData) eff.addressData = { ...eff.addressData, ...extractedResult.AddressData };
      if (extractedResult.SpouseData) {
        const spSur = extractedResult.SpouseData.spouse_surname || eff.spouseData.spouse_surname || "";
        const spFirst =
          extractedResult.SpouseData.spouse_first_names ||
          extractedResult.SpouseData.spouse_first_name ||
          (extractedResult.SpouseData as any).first_names ||
          (extractedResult.SpouseData as any).first_name ||
          eff.spouseData.spouse_first_names ||
          (eff.spouseData as any).spouse_first_name ||
          "";
        const spBirthSur =
          extractedResult.SpouseData.spouse_surname_at_birth ||
          eff.spouseData.spouse_surname_at_birth ||
          spSur;

        let spDobDay = extractedResult.SpouseData.spouse_dob_day || eff.spouseData.spouse_dob_day || "";
        let spDobMonth = extractedResult.SpouseData.spouse_dob_month || eff.spouseData.spouse_dob_month || "";
        let spDobYear = extractedResult.SpouseData.spouse_dob_year || eff.spouseData.spouse_dob_year || "";
        const rawDob =
          extractedResult.SpouseData.spouse_dob ||
          (extractedResult.SpouseData as any).dob ||
          (extractedResult.SpouseData as any).spouse_birth_date ||
          "";
        if (rawDob && (!spDobDay || !spDobYear)) {
          const parts = String(rawDob).split(/[\/\-\.]/);
          if (parts.length === 3) {
            if (parts[0].length === 4) {
              spDobYear = parts[0];
              spDobMonth = parts[1];
              spDobDay = parts[2];
            } else {
              spDobDay = parts[0];
              spDobMonth = parts[1];
              spDobYear = parts[2];
            }
          }
        }

        eff.spouseData = {
          ...eff.spouseData,
          ...extractedResult.SpouseData,
          spouse_surname: spSur,
          spouse_first_names: spFirst,
          spouse_surname_at_birth: spBirthSur,
          spouse_dob_day: spDobDay,
          spouse_dob_month: spDobMonth,
          spouse_dob_year: spDobYear,
          spouse_country_of_birth: extractedResult.SpouseData.spouse_country_of_birth || eff.spouseData.spouse_country_of_birth || "Sri Lanka",
          spouse_place_of_birth: extractedResult.SpouseData.spouse_place_of_birth || eff.spouseData.spouse_place_of_birth || "COLOMBO",
        };
        (eff.spouseData as any).spouse_first_name = spFirst;
      }

      const rawCivilEff = String(
        extractedResult.APPLICANT_CIVIL_STATUS ||
        extractedResult.PersonalData?.marital_status ||
        eff.applicant_civil_status ||
        eff.personalData.marital_status ||
        ""
      ).trim().toLowerCase();

      const isSingleEff = rawCivilEff.includes("singl") || rawCivilEff.includes("celibat") || rawCivilEff.includes("necasat") || rawCivilEff.includes("necăsăt") || rawCivilEff.includes("unmarr") || rawCivilEff === "1";
      const isMarriedEff = (rawCivilEff.includes("marr") || rawCivilEff.includes("casat") || rawCivilEff.includes("căsăt") || rawCivilEff === "2") && !isSingleEff;

      if (isSingleEff) {
        eff.applicant_civil_status = "Single";
        eff.personalData.marital_status = "Single";
        eff.spouseData = {
          spouse_surname: "",
          spouse_first_names: "",
          spouse_surname_at_birth: "",
          spouse_dob_day: "",
          spouse_dob_month: "",
          spouse_dob_year: "",
          spouse_country_of_birth: "",
          spouse_place_of_birth: "",
        };
        (eff.spouseData as any).spouse_first_name = "";
        if (eff.aiExtractedData) {
          eff.aiExtractedData.APPLICANT_CIVIL_STATUS = "Single";
          if (eff.aiExtractedData.PersonalData) eff.aiExtractedData.PersonalData.marital_status = "Single";
          eff.aiExtractedData.SpouseData = {
            spouse_surname: "",
            spouse_first_names: "",
            spouse_surname_at_birth: "",
            spouse_dob_day: "",
            spouse_dob_month: "",
            spouse_dob_year: "",
            spouse_country_of_birth: "",
            spouse_place_of_birth: "",
          };
        }
      } else if (isMarriedEff || (Boolean(extractedResult.SpouseData?.spouse_surname || extractedResult.SpouseData?.spouse_first_names) && !isSingleEff)) {
        eff.applicant_civil_status = "Married";
        eff.personalData.marital_status = "Married";
      }

      if (extractedResult.FamilyData) eff.familyData = { ...eff.familyData, ...extractedResult.FamilyData };
      if (extractedResult.CompanyContactData) {
        const comp = extractedResult.CompanyContactData;
        const compName = comp.name || comp.company_name || comp.employer_name || "";
        const compAddr = comp.full_address || comp.address || comp.company_address || "";
        const compPhone = comp.telephone_fax || comp.phone || comp.company_phone || "";
        const compEmail = comp.email || comp.company_email || "";
        const compWp = comp.work_permit_number || "";

        eff.companyContactData = {
          ...eff.companyContactData,
          ...comp,
          name: compName || eff.companyContactData.name,
          full_address: compAddr || eff.companyContactData.full_address,
          telephone_fax: compPhone || eff.companyContactData.telephone_fax,
          email: compEmail || eff.companyContactData.email,
          work_permit_number: compWp || eff.companyContactData.work_permit_number,
        };
        if (compWp) {
          eff.personalData.work_permit_number = compWp;
        }
        if (compName) {
          eff.hostData.hotel_name = compName;
          eff.costAndMeansData.host_name = compName;
        }
        if (compAddr) eff.hostData.host_address = compAddr;
        if (compEmail) {
          eff.hostData.host_email = compEmail;
          eff.hostData.email = compEmail;
        }
        if (compPhone) eff.hostData.host_phone = compPhone;
      }
      if (extractedResult.HostData) {
        eff.hostData = {
          ...eff.hostData,
          ...extractedResult.HostData,
          type_of_host: extractedResult.HostData.type_of_host || eff.hostData.type_of_host || "Company",
          hotel_name: extractedResult.HostData.hotel_name || eff.hostData.hotel_name || eff.companyContactData.name,
          host_address: extractedResult.HostData.host_address || eff.hostData.host_address || eff.companyContactData.full_address,
        };
        if (extractedResult.HostData.hotel_name) {
          eff.costAndMeansData.host_name = extractedResult.HostData.hotel_name;
        }
      }
      if (extractedResult.CostAndMeansData) eff.costAndMeansData = { ...eff.costAndMeansData, ...extractedResult.CostAndMeansData };
      if (extractedResult.JourneyDetailsData) eff.journeyDetailsData = { ...eff.journeyDetailsData, ...extractedResult.JourneyDetailsData };
      if (extractedResult.VisaRequestedDetails) eff.visaRequestedDetails = { ...eff.visaRequestedDetails, ...extractedResult.VisaRequestedDetails };
      if (extractedResult.VisaApplicationSelection) eff.selection = { ...eff.selection, ...extractedResult.VisaApplicationSelection };
    }
    return eff;
  };

  const handleDownloadPythonScript = async () => {
    setIsDownloadingScript(true);
    try {
      const effApplicant = getEffectiveApplicant();
      const response = await fetch("/api/generate-python-script", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          applicant: effApplicant,
          config: {
            documentsFolderPath,
            targetApplicationUrl: startUrl,
          },
        }),
      });
      const data = await response.json();
      if (data.success && data.script) {
        const blob = new Blob([data.script], { type: "text/x-python;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = data.filename || `evisa_automation_playwright_${applicant.fileNumber || "script"}.py`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }
    } catch (err) {
      console.error("Failed to download script:", err);
    } finally {
      setIsDownloadingScript(false);
    }
  };

  const handleDownloadBatLauncher = async () => {
    setIsDownloadingBat(true);
    try {
      const effApplicant = getEffectiveApplicant();
      const response = await fetch("/api/generate-python-script", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          applicant: effApplicant,
          config: {
            documentsFolderPath,
            targetApplicationUrl: startUrl,
          },
        }),
      });
      const data = await response.json();
      if (data.success && data.batContent) {
        const blob = new Blob([data.batContent], { type: "application/x-bat;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = data.batFilename || `run_evisa_automation_${applicant.fileNumber || "launcher"}.bat`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }
    } catch (err) {
      console.error("Failed to download batch launcher:", err);
    } finally {
      setIsDownloadingBat(false);
    }
  };

  const handleDownloadZipPackage = async () => {
    setIsDownloadingZip(true);
    try {
      const effApplicant = getEffectiveApplicant();
      const fileNumber = effApplicant?.fileNumber || applicant?.fileNumber || "E25110721257414";
      const folderPath = documentsFolderPath || effApplicant?.documentsFolderPath || "C:/VisaDocs/";
      const scriptFilename = `evisa_automation_${fileNumber}.py`;
      const batFilename = `run_evisa_automation_${fileNumber}.bat`;

      let downloadedSuccessfully = false;

      // Primary: Try server-side binary ZIP endpoint
      try {
        const response = await fetch("/api/download-automation-package", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            applicant: effApplicant,
            config: {
              documentsFolderPath,
              targetApplicationUrl: startUrl,
            },
          }),
        });
        if (response.ok) {
          const blob = await response.blob();
          if (blob && blob.size > 0) {
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `eVisa_Automation_Package_${fileNumber}.zip`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            downloadedSuccessfully = true;
          }
        }
      } catch (srvErr) {
        console.warn("Server ZIP endpoint failed, falling back to client-side JSZip generator:", srvErr);
      }

      // Secondary Fallback: Generate ZIP directly via client JSZip using generated script & templates
      if (!downloadedSuccessfully) {
        const genRes = await fetch("/api/generate-python-script", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            applicant: effApplicant,
            config: {
              documentsFolderPath,
              targetApplicationUrl: startUrl,
            },
          }),
        });

        const genData = await genRes.json();
        if (genData.success && genData.script) {
          const zip = new JSZip();
          zip.file(scriptFilename, genData.script);
          zip.file(batFilename, genData.batContent || "");
          
          const chromeDebugBat = `@echo off\r\ntitle Launch Google Chrome with Remote Debugging (Port 9222)\r\ncd /d "%~dp0"\r\necho ==============================================================================\r\necho Launching Google Chrome with Remote Debugging enabled on Port 9222...\r\necho Profile: transarabianofficial@gmail.com\r\necho This preserves your active tabs, logins, and cookies while allowing Playwright\r\necho to attach and open a NEW TAB automatically without restarting your browser!\r\necho ==============================================================================\r\necho.\r\nif exist "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" (\r\n    start "" "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222 --restore-last-session\r\n    echo Chrome launched successfully with Port 9222!\r\n) else if exist "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe" (\r\n    start "" "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222 --restore-last-session\r\n    echo Chrome launched successfully with Port 9222!\r\n) else if exist "%LOCALAPPDATA%\\Google\\Chrome\\Application\\chrome.exe" (\r\n    start "" "%LOCALAPPDATA%\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222 --restore-last-session\r\n    echo Chrome launched successfully with Port 9222!\r\n) else (\r\n    start chrome.exe --remote-debugging-port=9222 --restore-last-session\r\n    echo Chrome launched from PATH!\r\n)\r\necho.\r\necho Now you can run ${batFilename} - it will attach to this Chrome and open a new tab!\r\ntimeout /t 5\r\n`;

          const requirementsTxt = `playwright>=1.45.0,<2.0.0\npython-dotenv>=1.0.0\nopencv-python>=4.8.0\nnumpy>=1.24.0\nPillow>=10.0.0\n`;
          const readmeTxt = `==============================================================================\r\ne-Visa Romania Playwright & OpenCV Automation Package\r\nApplicant File: ${fileNumber}\r\n==============================================================================\r\n\r\nINSTRUCTIONS TO RUN ON YOUR LOCAL WINDOWS PC:\r\n\r\n1. Extract this entire ZIP folder to your preferred folder (e.g. C:\\VisaDocs\\ or Desktop).\r\n2. Supporting Documents & Photo Location:\r\n   - Ensure your supporting document files are in: ${folderPath}\r\n   - Required filenames:\r\n     * photo.jpg               (Applicant photo - OpenCV automatically recognizes face, resizes, and calibrates green frame coordinates)\r\n     * work_permit.pdf         (Romanian IGI Work Permit)\r\n     * AGREEMENT.pdf           (Means of Support / Accommodation Agreement)\r\n     * police_clearance.pdf    (Criminal Record Clearance)\r\n     * medical_insurance.pdf   (Travel Medical Insurance)\r\n     * passport.pdf            (Valid Travel Document / Passport Copy)\r\n\r\n3. Launch Automation:\r\n   - Double-click "${batFilename}".\r\n   - The launcher will automatically verify Python, install Playwright, OpenCV, and Chromium,\r\n     launch the browser in headful mode, and execute the automated data filling,\r\n     photo recognition/cropping, and document uploading steps.\r\n`;

          zip.file("Start_Chrome_Debug.bat", chromeDebugBat);
          zip.file("requirements.txt", requirementsTxt);
          zip.file("README.txt", readmeTxt);

          const zipBlob = await zip.generateAsync({ type: "blob", compression: "DEFLATE" });
          const url = URL.createObjectURL(zipBlob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `eVisa_Automation_Package_${fileNumber}.zip`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
          downloadedSuccessfully = true;
        } else {
          throw new Error(genData.error || "Failed to generate automation code for ZIP package");
        }
      }
    } catch (err: any) {
      console.error("Failed to download zip package:", err);
      alert(`Download notice: ${err?.message || "Could not bundle package. Please try downloading Python script or .BAT launcher directly."}`);
    } finally {
      setIsDownloadingZip(false);
    }
  };

  const handlePreviewCode = async () => {
    try {
      const effApplicant = getEffectiveApplicant();
      const response = await fetch("/api/generate-python-script", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          applicant: effApplicant,
          config: {
            documentsFolderPath,
            targetApplicationUrl: startUrl,
          },
        }),
      });
      const data = await response.json();
      if (data.success && data.script) {
        setPreviewCode(data.script);
        setShowCodePreview(true);
      }
    } catch (err) {
      console.error("Failed to preview script:", err);
    }
  };

  // Validation Engine Summary Memo
  const validationSummary: ValidationSummary = useMemo(() => {
    const eff = getEffectiveApplicant();
    return validateExtractedData(extractedResult || eff, {
      applicantText: inputs.applicant,
      spouseText: inputs.spouse,
      companyText: inputs.company,
      otherText: inputs.other,
      ocrSummaryText: extractedResult?._ocrTextSummary || "",
    });
  }, [extractedResult, inputs, applicant, documentsFolderPath, startUrl]);

  // Validation Gate Action Wrappers
  const triggerApplyToState = (force = false) => {
    if (!force && validationSummary.errorCount > 0) {
      setPendingScriptAction("apply");
      setShowValidationGateModal(true);
      return;
    }
    handleApplyToState();
  };

  const triggerDownloadPythonScript = (force = false) => {
    if (!force && validationSummary.errorCount > 0) {
      setPendingScriptAction("py");
      setShowValidationGateModal(true);
      return;
    }
    handleDownloadPythonScript();
  };

  const triggerDownloadBatLauncher = (force = false) => {
    if (!force && validationSummary.errorCount > 0) {
      setPendingScriptAction("bat");
      setShowValidationGateModal(true);
      return;
    }
    handleDownloadBatLauncher();
  };

  const triggerDownloadZipPackage = (force = false) => {
    if (!force && validationSummary.errorCount > 0) {
      setPendingScriptAction("zip");
      setShowValidationGateModal(true);
      return;
    }
    handleDownloadZipPackage();
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">
      {/* Header section */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div className="flex items-center space-x-3">
          <div className="p-3 bg-purple-500/10 text-purple-400 rounded-xl border border-purple-500/20">
            <Sparkles className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-100 flex items-center space-x-2">
              <span>AI Document Schematics & Extraction Hub</span>
              <span className="bg-purple-500/20 text-purple-300 text-[11px] px-2.5 py-0.5 rounded-full font-mono font-bold">
                Gemini Flash OCR Engine
              </span>
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Simultaneous intelligent extraction for Applicant Passport, Romanian Work Permits, Spouse ID & Travel Documents.
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={handleLoadSample}
            className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-xl border border-slate-700 transition-colors flex items-center space-x-1.5"
            title="Load sample data"
          >
            <FileSpreadsheet className="w-3.5 h-3.5 text-cyan-400" />
            <span>Load Sample Data</span>
          </button>

          {extractedResult && (
            <button
              onClick={() => triggerApplyToState()}
              className="inline-flex items-center space-x-2 px-4 py-2 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold text-xs rounded-xl shadow-lg shadow-emerald-900/30 transition-all active:scale-95"
            >
              <Check className="w-4 h-4" />
              <span>{appliedSuccess ? "Applied to Master State!" : "Apply to Master Schematics"}</span>
            </button>
          )}
        </div>
      </div>

      {/* AI Document Validation Checker Health Banner */}
      <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs shadow-inner">
        <div className="flex items-center space-x-3">
          {validationSummary.errorCount > 0 ? (
            <div className="p-2.5 bg-rose-500/10 text-rose-400 rounded-xl border border-rose-500/20 shrink-0">
              <ShieldAlert className="w-5 h-5 animate-pulse" />
            </div>
          ) : validationSummary.warningCount > 0 ? (
            <div className="p-2.5 bg-amber-500/10 text-amber-400 rounded-xl border border-amber-500/20 shrink-0">
              <AlertTriangle className="w-5 h-5" />
            </div>
          ) : (
            <div className="p-2.5 bg-emerald-500/10 text-emerald-400 rounded-xl border border-emerald-500/20 shrink-0">
              <ShieldCheck className="w-5 h-5" />
            </div>
          )}
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-bold text-slate-100 flex items-center space-x-1.5">
                <span>AI Extractor Document Validation Checker</span>
              </span>
              <span
                className={`px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold border ${
                  validationSummary.healthScore >= 90
                    ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
                    : validationSummary.healthScore >= 70
                    ? "bg-amber-500/20 text-amber-300 border-amber-500/30"
                    : "bg-rose-500/20 text-rose-300 border-rose-500/30"
                }`}
              >
                {validationSummary.healthScore}% Verification Score ({validationSummary.verifiedCount}/{validationSummary.totalFields} Verified)
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mt-0.5">
              {validationSummary.errorCount > 0
                ? `Discrepancy Alert: ${validationSummary.errorCount} field(s) require review before generating automation script.`
                : validationSummary.warningCount > 0
                ? `${validationSummary.warningCount} field(s) formatted differently from source document text.`
                : "All extracted passport numbers, dates, applicant names, birthdates, address & work permit numbers exactly match documents data."}
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={() => setViewMode("validation")}
            className="px-3 py-1.5 bg-purple-500/10 hover:bg-purple-500/20 text-purple-300 border border-purple-500/30 rounded-lg font-bold text-[11px] flex items-center space-x-1.5 transition-all shadow-sm"
          >
            <FileCheck className="w-3.5 h-3.5 text-purple-300" />
            <span>Open Validation Audit Table</span>
          </button>
        </div>
      </div>

      {/* Category Navigation Tabs */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <button
          onClick={() => setActiveCategory("applicant")}
          className={`flex items-center justify-between px-3 py-2.5 rounded-xl text-xs font-bold transition-all ${
            activeCategory === "applicant"
              ? "bg-purple-500/20 text-purple-300 border border-purple-500/40 shadow-lg"
              : "bg-slate-950/60 text-slate-400 hover:text-slate-200 border border-slate-800"
          }`}
        >
          <div className="flex items-center space-x-2">
            <User className="w-4 h-4" />
            <span>1. Applicant Data</span>
          </div>
          {imageFiles.applicant.length > 0 && (
            <span className="text-[10px] bg-purple-500/30 text-purple-200 px-1.5 py-0.5 rounded-full font-mono">
              {imageFiles.applicant.length}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveCategory("spouse")}
          className={`flex items-center justify-between px-3 py-2.5 rounded-xl text-xs font-bold transition-all ${
            activeCategory === "spouse"
              ? "bg-purple-500/20 text-purple-300 border border-purple-500/40 shadow-lg"
              : "bg-slate-950/60 text-slate-400 hover:text-slate-200 border border-slate-800"
          }`}
        >
          <div className="flex items-center space-x-2">
            <Heart className="w-4 h-4" />
            <span>2. Spouse Data</span>
          </div>
          {imageFiles.spouse.length > 0 && (
            <span className="text-[10px] bg-purple-500/30 text-purple-200 px-1.5 py-0.5 rounded-full font-mono">
              {imageFiles.spouse.length}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveCategory("company")}
          className={`flex items-center justify-between px-3 py-2.5 rounded-xl text-xs font-bold transition-all ${
            activeCategory === "company"
              ? "bg-purple-500/20 text-purple-300 border border-purple-500/40 shadow-lg"
              : "bg-slate-950/60 text-slate-400 hover:text-slate-200 border border-slate-800"
          }`}
        >
          <div className="flex items-center space-x-2">
            <Building2 className="w-4 h-4" />
            <span>3. Company Details</span>
          </div>
          {imageFiles.company.length > 0 && (
            <span className="text-[10px] bg-purple-500/30 text-purple-200 px-1.5 py-0.5 rounded-full font-mono">
              {imageFiles.company.length}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveCategory("other")}
          className={`flex items-center justify-between px-3 py-2.5 rounded-xl text-xs font-bold transition-all ${
            activeCategory === "other"
              ? "bg-purple-500/20 text-purple-300 border border-purple-500/40 shadow-lg"
              : "bg-slate-950/60 text-slate-400 hover:text-slate-200 border border-slate-800"
          }`}
        >
          <div className="flex items-center space-x-2">
            <Layers className="w-4 h-4" />
            <span>4. Other Documents</span>
          </div>
          {imageFiles.other.length > 0 && (
            <span className="text-[10px] bg-purple-500/30 text-purple-200 px-1.5 py-0.5 rounded-full font-mono">
              {imageFiles.other.length}
            </span>
          )}
        </button>
      </div>

      {/* Main Grid: Input Column & Extracted Output Column */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Column: Input text & Document upload */}
        <div className="space-y-4">
          <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800">
            <div className="flex items-center justify-between mb-2">
              <label className="block text-xs font-semibold text-cyan-400 uppercase tracking-wider">
                {activeCategory === "applicant" && "Upload Passport, Work Permit & Police Clearance"}
                {activeCategory === "spouse" && "Upload Spouse ID Card / Marriage Certificate"}
                {activeCategory === "company" && "Upload Company Invitation & Host Details"}
                {activeCategory === "other" && "Upload Insurance / Tickets / Other Documents"}
              </label>
              <span className="text-[10px] text-slate-400 font-mono">
                {imageFiles[activeCategory].length} file(s) attached
              </span>
            </div>

            <div
              onDrop={(e) => handleDrop(activeCategory, e)}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              className={`relative border-2 border-dashed rounded-xl p-5 bg-slate-950 text-center transition-all cursor-pointer ${
                isDragging ? "border-cyan-400 bg-cyan-950/30 scale-[1.01]" : "border-slate-700 hover:border-cyan-500/50"
              }`}
            >
              <input
                type="file"
                multiple
                accept="application/pdf,image/jpeg,image/png,image/webp,.pdf,.jpg,.jpeg,.png"
                onChange={(e) => handleFileUpload(activeCategory, e)}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
              />
              <Upload className={`w-7 h-7 mx-auto mb-1.5 transition-transform ${isDragging ? "text-cyan-300 scale-110 animate-bounce" : "text-cyan-400"}`} />
              <p className="text-xs font-medium text-slate-300">
                Drag & drop PDF / Images here or click to browse
              </p>
              <p className="text-[10px] text-slate-500 mt-0.5">
                Supports PDF, JPG, PNG documents up to 50MB
              </p>
            </div>

            {/* List of uploaded files with remove button */}
            {imageFiles[activeCategory].length > 0 && (
              <div className="mt-3 space-y-2 max-h-36 overflow-y-auto pr-1">
                <span className="text-[11px] font-semibold text-slate-400 uppercase">
                  Uploaded in [{activeCategory.toUpperCase()}]:
                </span>
                {imageFiles[activeCategory].map((file, idx) => (
                  <div key={idx} className="flex items-center justify-between bg-slate-900 px-3 py-1.5 rounded-lg border border-slate-800 text-xs">
                    <div className="flex items-center space-x-2 truncate">
                      <FileText className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                      <span className="text-slate-200 truncate font-mono">{file.name}</span>
                    </div>
                    <button
                      onClick={() => handleRemoveFile(activeCategory, idx)}
                      className="text-rose-400 hover:text-rose-300 text-[11px] font-bold px-1.5 py-0.5 rounded bg-rose-500/10 hover:bg-rose-500/20 transition-colors ml-2"
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5 flex items-center justify-between">
              <span>{activeCategory.toUpperCase()} Text & Intelligence Input</span>
              <span className="text-[10px] text-slate-500 font-mono">Editable OCR Text / Schematics</span>
            </label>
            <textarea
              value={inputs[activeCategory]}
              onChange={(e) => setInputs({ ...inputs, [activeCategory]: e.target.value })}
              rows={8}
              className="w-full bg-slate-950 text-slate-200 font-mono text-xs p-3.5 rounded-xl border border-slate-800 focus:border-purple-500 focus:outline-none focus:ring-1 focus:ring-purple-500"
              placeholder="Paste document text or extracted OCR text..."
            />
          </div>

          {/* AI Model Selector & Quota Options */}
          <div className="bg-slate-900/90 p-3 rounded-xl border border-slate-800 space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-purple-300 flex items-center space-x-1.5">
                <Sparkles className="w-3.5 h-3.5 text-purple-400" />
                <span>AI Extraction Engine & Quota Fallback</span>
              </label>
              <span className="text-[10px] text-slate-400 font-mono">Select Active Model</span>
            </div>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="w-full bg-slate-950 text-slate-200 text-xs font-mono p-2.5 rounded-lg border border-slate-700 focus:border-purple-500 focus:outline-none"
            >
              <option value="auto">⚡ Auto-Select / High Availability Pipeline (Gemini 3.7 Flash / 3.5 Flash)</option>
              <option value="gemini-3.7-flash">Gemini 3.7 Flash (High Accuracy Reasoning & Vision)</option>
              <option value="gemini-3.5-flash">Gemini 3.5 Flash (Balanced Intelligence & High Speed)</option>
              <option value="gemini-3.5-flash-lite">Gemini 3.5 Flash Lite (Highest Quota & High Speed)</option>
              <option value="gemini-3.6-flash">Gemini 3.6 Flash (High Availability, Multimodal OCR)</option>
              <option value="gemini-3.1-flash-lite">Gemini 3.1 Flash Lite (High Speed & Highest Quota)</option>
              <option value="gemini-3.8-flash">Gemini 3.8 Flash</option>
              <option value="gemini-flash-latest">Gemini Flash Latest</option>
              <option value="gemini-3.1-pro-preview">Gemini 3.1 Pro (Deep Document Reasoning)</option>
              <option value="regex_offline">🛠️ Offline Regex Heuristic Engine (No API Quota Required)</option>
            </select>
            <p className="text-[11px] text-slate-400 leading-tight">
              If your API key reaches its rate limit or quota limit (e.g. 429 RESOURCE_EXHAUSTED), switch models or choose <strong className="text-purple-300">Offline Regex Heuristic Engine</strong> to extract applicant details locally without API credits.
            </p>
          </div>

          <button
            onClick={handleRunAiExtraction}
            disabled={isExtracting}
            className={`w-full flex items-center justify-center space-x-2 py-3 rounded-xl font-bold text-xs transition-all shadow-lg ${
              isExtracting
                ? "bg-purple-900/60 text-purple-200 cursor-wait animate-pulse"
                : "bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white shadow-purple-900/30"
            }`}
          >
            {isExtracting ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin text-purple-300" />
                <span>Extracting All Sections with {selectedModel === "regex_offline" ? "Offline Regex" : "Gemini AI"}...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4 text-purple-200" />
                <span>⚡ Run Simultaneous Extraction (Applicant, Permit, Spouse, Company)</span>
              </>
            )}
          </button>

          {lastModelUsed && (
            <div className={`p-3 rounded-xl border text-xs flex items-center justify-between ${
              usedFallbackEngine
                ? "bg-amber-500/10 border-amber-500/30 text-amber-300"
                : "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
            }`}>
              <div className="flex items-center space-x-2">
                {usedFallbackEngine ? (
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                ) : (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                )}
                <span>
                  {usedFallbackEngine
                    ? `Notice: Quota/Limit reached on primary model. Extracted via ${lastModelUsed}.`
                    : `Extraction completed successfully using ${lastModelUsed}.`}
                </span>
              </div>
              <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-slate-950 border border-slate-800 font-bold shrink-0 ml-2">
                {lastModelUsed}
              </span>
            </div>
          )}

          {extractError && (
            <div className="p-3 bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs rounded-xl flex items-start space-x-2">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              <span>{extractError}</span>
            </div>
          )}
        </div>

        {/* Right Column: Interactive Extracted Fields & Data Mapping */}
        <div className="bg-slate-950 rounded-xl border border-slate-800 p-4 flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center space-x-2">
                <FileText className="w-4 h-4 text-purple-400" />
                <span className="text-xs font-bold text-slate-200 uppercase tracking-wider">
                  Extracted Intelligence Workspace
                </span>
              </div>
              <div className="flex items-center space-x-1.5">
                <button
                  onClick={() => setViewMode("visual")}
                  className={`px-2.5 py-1 text-[11px] font-bold rounded-lg transition-colors ${
                    viewMode === "visual"
                      ? "bg-purple-500/20 text-purple-300 border border-purple-500/40"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Visual Form
                </button>
                <button
                  onClick={() => setViewMode("validation")}
                  className={`px-2.5 py-1 text-[11px] font-bold rounded-lg transition-colors flex items-center space-x-1 ${
                    viewMode === "validation"
                      ? "bg-purple-500/20 text-purple-300 border border-purple-500/40"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <FileCheck className="w-3 h-3 text-cyan-400" />
                  <span>Validation Audit</span>
                  <span className={`px-1.5 py-0.2 text-[9px] rounded-full font-mono ${
                    validationSummary.errorCount > 0
                      ? "bg-rose-500/30 text-rose-300"
                      : "bg-emerald-500/30 text-emerald-300"
                  }`}>
                    {validationSummary.verifiedCount}/{validationSummary.totalFields}
                  </span>
                </button>
                <button
                  onClick={() => setViewMode("json")}
                  className={`px-2.5 py-1 text-[11px] font-bold rounded-lg transition-colors ${
                    viewMode === "json"
                      ? "bg-purple-500/20 text-purple-300 border border-purple-500/40"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Raw JSON
                </button>
                {extractedResult && (
                  <button
                    onClick={() => navigator.clipboard.writeText(JSON.stringify(extractedResult, null, 2))}
                    className="p-1 text-slate-400 hover:text-cyan-400"
                    title="Copy JSON"
                  >
                    <Copy className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>

            {/* Extracted Content Body */}
            {viewMode === "visual" ? (
              <div className="mt-3 space-y-4 max-h-[460px] overflow-y-auto pr-1">
                {/* 1. Applicant Personal Data & Work Permit Card */}
                <div className="bg-slate-900/90 p-3.5 rounded-xl border border-purple-500/40 space-y-3">
                  <div className="flex items-center justify-between pb-1.5 border-b border-purple-500/20">
                    <span className="text-xs font-bold text-purple-300 flex items-center space-x-1.5">
                      <User className="w-4 h-4 text-purple-400" />
                      <span>Applicant Personal Data & Work Permit</span>
                    </span>
                    <span className="text-[10px] bg-purple-500/20 text-purple-200 border border-purple-500/30 px-2 py-0.5 rounded font-mono font-bold">
                      Passport & Aviz de Muncă
                    </span>
                  </div>

                  {/* Work Permit Number (Prominently displayed in Applicant Data section) */}
                  <div className="bg-cyan-950/40 p-2.5 rounded-lg border border-cyan-500/40 space-y-1">
                    <div className="flex items-center justify-between">
                      <label className="text-[11px] text-cyan-300 font-bold flex items-center space-x-1">
                        <FileText className="w-3.5 h-3.5 text-cyan-400" />
                        <span>Work Permit Number (Aviz de Muncă)</span>
                      </label>
                      <span className="text-[9px] text-cyan-400 font-mono">În baza cererii nr.</span>
                    </div>
                    <input
                      type="text"
                      value={
                        extractedResult?.PersonalData?.work_permit_number ||
                        extractedResult?.CompanyContactData?.work_permit_number ||
                        applicant.companyContactData.work_permit_number ||
                        "WP-2026-991823"
                      }
                      onChange={(e) => {
                        const val = e.target.value;
                        setExtractedResult((prev: any) => ({
                          ...(prev || {}),
                          PersonalData: { ...(prev?.PersonalData || {}), work_permit_number: val },
                          CompanyContactData: { ...(prev?.CompanyContactData || {}), work_permit_number: val },
                        }));
                      }}
                      className="w-full bg-slate-950 border border-cyan-400 rounded p-1.5 text-xs text-cyan-200 font-mono font-bold shadow-inner"
                      placeholder="e.g. WP-2026-991823"
                    />
                  </div>

                  {/* Applicant Surname, First Names, Phone Number */}
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-[10px] text-slate-400 font-medium">Applicant Surname</span>
                      <input
                        type="text"
                        value={extractedResult?.PersonalData?.surname ?? applicant.personalData.surname ?? ""}
                        onChange={(e) => {
                          const val = e.target.value;
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            PersonalData: { ...(prev?.PersonalData || {}), surname: val },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono"
                      />
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-400 font-medium">Applicant First Names</span>
                      <input
                        type="text"
                        value={extractedResult?.PersonalData?.first_names ?? applicant.personalData.first_names ?? ""}
                        onChange={(e) => {
                          const val = e.target.value;
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            PersonalData: { ...(prev?.PersonalData || {}), first_names: val },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-[10px] text-slate-400 font-medium">Surname at Birth</span>
                      <input
                        type="text"
                        value={extractedResult?.PersonalData?.surname_at_birth ?? applicant.personalData.surname_at_birth ?? ""}
                        onChange={(e) => {
                          const val = e.target.value;
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            PersonalData: { ...(prev?.PersonalData || {}), surname_at_birth: val },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono"
                      />
                    </div>
                    <div>
                      <span className="text-[10px] text-cyan-300 font-semibold flex items-center space-x-1">
                        <PhoneCall className="w-3 h-3 text-cyan-400" />
                        <span>Applicant Phone Number</span>
                      </span>
                      <input
                        type="text"
                        value={extractedResult?.PersonalData?.phone_number ?? applicant.personalData.phone_number ?? ""}
                        onChange={(e) => {
                          const val = e.target.value;
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            PersonalData: { ...(prev?.PersonalData || {}), phone_number: val },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-cyan-500/60 rounded p-1.5 text-xs text-cyan-200 font-mono font-bold"
                        placeholder="+94 77 123 4567"
                      />
                    </div>
                  </div>

                  {/* Date of Birth & Sex / Marital Status */}
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-[10px] text-slate-400">Date of Birth (DD / MM / YYYY)</span>
                      <div className="grid grid-cols-3 gap-1">
                        <input
                          type="text"
                          placeholder="DD"
                          value={extractedResult?.PersonalData?.dob_day ?? applicant.personalData.dob_day ?? ""}
                          onChange={(e) => {
                            const val = e.target.value;
                            setExtractedResult((prev: any) => ({
                              ...(prev || {}),
                              PersonalData: { ...(prev?.PersonalData || {}), dob_day: val },
                            }));
                          }}
                          className="bg-slate-950 border border-slate-700 rounded p-1 text-xs text-slate-200 font-mono text-center"
                        />
                        <input
                          type="text"
                          placeholder="MM"
                          value={extractedResult?.PersonalData?.dob_month ?? applicant.personalData.dob_month ?? ""}
                          onChange={(e) => {
                            const val = e.target.value;
                            setExtractedResult((prev: any) => ({
                              ...(prev || {}),
                              PersonalData: { ...(prev?.PersonalData || {}), dob_month: val },
                            }));
                          }}
                          className="bg-slate-950 border border-slate-700 rounded p-1 text-xs text-slate-200 font-mono text-center"
                        />
                        <input
                          type="text"
                          placeholder="YYYY"
                          value={extractedResult?.PersonalData?.dob_year ?? applicant.personalData.dob_year ?? ""}
                          onChange={(e) => {
                            const val = e.target.value;
                            setExtractedResult((prev: any) => ({
                              ...(prev || {}),
                              PersonalData: { ...(prev?.PersonalData || {}), dob_year: val },
                            }));
                          }}
                          className="bg-slate-950 border border-slate-700 rounded p-1 text-xs text-slate-200 font-mono text-center"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-1">
                      <div>
                        <span className="text-[10px] text-slate-400">Sex</span>
                        <select
                          value={extractedResult?.PersonalData?.sex ?? applicant.personalData.sex ?? "Female"}
                          onChange={(e) => {
                            const val = e.target.value;
                            setExtractedResult((prev: any) => ({
                              ...(prev || {}),
                              PersonalData: { ...(prev?.PersonalData || {}), sex: val },
                            }));
                          }}
                          className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono"
                        >
                          <option value="Female">Female</option>
                          <option value="Male">Male</option>
                        </select>
                      </div>
                      <div>
                        <span className="text-[10px] text-slate-400">Marital</span>
                        <input
                          type="text"
                          value={extractedResult?.APPLICANT_CIVIL_STATUS ?? extractedResult?.PersonalData?.marital_status ?? applicant.applicant_civil_status ?? applicant.personalData.marital_status ?? "Single"}
                          onChange={(e) => {
                            const val = e.target.value;
                            const isSingle = val.toLowerCase().includes("singl") || val.toLowerCase().includes("celibat") || val.toLowerCase().includes("necasat") || val.toLowerCase().includes("necăsăt") || val.toLowerCase().includes("unmarr") || val === "1";
                            setExtractedResult((prev: any) => ({
                              ...(prev || {}),
                              APPLICANT_CIVIL_STATUS: isSingle ? "Single" : val,
                              PersonalData: { ...(prev?.PersonalData || {}), marital_status: isSingle ? "Single" : val },
                              SpouseData: isSingle ? {
                                spouse_surname: "",
                                spouse_first_names: "",
                                spouse_surname_at_birth: "",
                                spouse_dob_day: "",
                                spouse_dob_month: "",
                                spouse_dob_year: "",
                                spouse_country_of_birth: "",
                                spouse_place_of_birth: "",
                              } : (prev?.SpouseData || {})
                            }));
                            if (onUpdateApplicant) {
                              onUpdateApplicant({
                                ...applicant,
                                applicant_civil_status: isSingle ? "Single" : val,
                                personalData: {
                                  ...applicant.personalData,
                                  marital_status: isSingle ? "Single" : val
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
                                  }
                                } : {})
                              });
                            }
                          }}
                          className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono"
                        />
                      </div>
                    </div>
                  </div>
                </div>

                {/* 2. Parents & Family Data Card */}
                <div className="bg-slate-900/90 p-3.5 rounded-xl border border-indigo-500/40 space-y-2.5">
                  <div className="flex items-center justify-between pb-1 border-b border-indigo-500/20">
                    <span className="text-xs font-bold text-indigo-300 flex items-center space-x-1.5">
                      <User className="w-3.5 h-3.5 text-indigo-400" />
                      <span>Parents & Family Data (Father & Mother Names)</span>
                    </span>
                    <span className="text-[10px] bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 px-2 py-0.5 rounded font-mono">
                      Family Schematics
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-xs">
                    {(() => {
                      const currentAppSur = extractedResult?.PersonalData?.surname || applicant.personalData.surname || "";
                      const rawFatherSur = extractedResult?.FamilyData?.father_surname !== undefined
                        ? extractedResult.FamilyData.father_surname
                        : (applicant.familyData.father_surname || "PERERA");
                      const rawFatherFirst = extractedResult?.FamilyData?.father_first_name !== undefined
                        ? extractedResult.FamilyData.father_first_name
                        : (applicant.familyData.father_first_name || "SUNIL");
                      const resolvedFather = normalizeFamilyFatherData(
                        { father_surname: rawFatherSur, father_first_name: rawFatherFirst },
                        currentAppSur
                      );

                      return (
                        <>
                          <div>
                            <span className="text-[10px] text-slate-400">Father Surname</span>
                            <input
                              type="text"
                              value={resolvedFather.father_surname || "PERERA"}
                              onChange={(e) => {
                                const val = e.target.value;
                                setExtractedResult((prev: any) => ({
                                  ...(prev || {}),
                                  FamilyData: { ...(prev?.FamilyData || {}), father_surname: val },
                                }));
                              }}
                              className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono"
                            />
                          </div>
                          <div>
                            <span className="text-[10px] text-slate-400">Father First Name</span>
                            <input
                              type="text"
                              value={resolvedFather.father_first_name || "SUNIL"}
                              onChange={(e) => {
                                const val = e.target.value;
                                setExtractedResult((prev: any) => ({
                                  ...(prev || {}),
                                  FamilyData: { ...(prev?.FamilyData || {}), father_first_name: val },
                                }));
                              }}
                              className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono"
                            />
                          </div>
                        </>
                      );
                    })()}
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-[10px] text-slate-400">Mother Surname</span>
                      <input
                        type="text"
                        value={
                          extractedResult?.FamilyData?.mother_surname ||
                          applicant.familyData.mother_surname ||
                          "FERNANDO"
                        }
                        onChange={(e) => {
                          const val = e.target.value;
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            FamilyData: { ...(prev?.FamilyData || {}), mother_surname: val },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono"
                      />
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-400">Mother First Name</span>
                      <input
                        type="text"
                        value={
                          extractedResult?.FamilyData?.mother_first_name ||
                          applicant.familyData.mother_first_name ||
                          "KANTI"
                        }
                        onChange={(e) => {
                          const val = e.target.value;
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            FamilyData: { ...(prev?.FamilyData || {}), mother_first_name: val },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono"
                      />
                    </div>
                  </div>
                </div>

                {/* 3. Travel Document & Occupation Box */}
                <div className="bg-slate-900/90 p-3.5 rounded-xl border border-amber-500/30 space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-amber-400 flex items-center space-x-1.5">
                      <Briefcase className="w-3.5 h-3.5" />
                      <span>Travel Document & 07. Current Occupation Mapping</span>
                    </span>
                    <span className="text-[10px] bg-amber-500/10 text-amber-300 border border-amber-500/20 px-2 py-0.5 rounded font-mono">
                      #Ocupatie & #AltaOcupatie
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-[10px] text-slate-400">Passport Number</span>
                      <input
                        type="text"
                        value={extractedResult?.TravelDocument?.passport_number || applicant.travelDoc.passport_number}
                        onChange={(e) => {
                          const val = e.target.value;
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            TravelDocument: { ...(prev?.TravelDocument || {}), passport_number: val },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono"
                      />
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-400">Issuing Authority</span>
                      <input
                        type="text"
                        value={extractedResult?.TravelDocument?.issuing_authority || applicant.travelDoc.issuing_authority}
                        onChange={(e) => {
                          const val = e.target.value;
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            TravelDocument: { ...(prev?.TravelDocument || {}), issuing_authority: val },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono"
                      />
                    </div>
                     <div>
                      <span className="text-[10px] text-emerald-400 font-medium">Passport Issue Date (MM/DD/YYYY)</span>
                      <input
                        type="text"
                        placeholder="MM/DD/YYYY"
                        value={extractedResult?.TravelDocument?.date_of_issue || applicant.travelDoc.date_of_issue || ""}
                        onChange={(e) => {
                          const val = e.target.value;
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            TravelDocument: { ...(prev?.TravelDocument || {}), date_of_issue: val },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-slate-700 focus:border-emerald-500 rounded p-1.5 text-xs text-emerald-300 font-mono"
                      />
                    </div>
                    <div>
                      <span className="text-[10px] text-emerald-400 font-medium">Passport Expiry Date (MM/DD/YYYY)</span>
                      <input
                        type="text"
                        placeholder="MM/DD/YYYY"
                        value={extractedResult?.TravelDocument?.valid_until || applicant.travelDoc.valid_until || ""}
                        onChange={(e) => {
                          const val = e.target.value;
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            TravelDocument: { ...(prev?.TravelDocument || {}), valid_until: val },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-slate-700 focus:border-emerald-500 rounded p-1.5 text-xs text-emerald-300 font-mono"
                      />
                    </div>
                  </div>

                  {/* Main Occupation Dropdown (Official eVisa ID List) */}
                  <div className="pt-2 border-t border-slate-800 space-y-2">
                    <div>
                      <label className="text-[10px] text-amber-300 font-semibold block mb-0.5">
                        Occupation Selector <span className="text-amber-400 font-mono text-[10px] ml-1">(Official eVisa ID List)</span>
                      </label>
                      <select
                        value={
                          extractedResult?.TravelDocument?.occupation_id ||
                          applicant.travelDoc.occupation_id ||
                          (extractedResult?.TravelDocument?.current_occupation === "Other" || applicant.travelDoc.current_occupation === "Other" ? "1" : "1")
                        }
                        onChange={(e) => {
                          const selectedId = e.target.value;
                          const occ = EVISA_DEFAULT_OCCUPATIONS.find((o) => o.id === selectedId);
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            TravelDocument: {
                              ...(prev?.TravelDocument || {}),
                              occupation_id: selectedId,
                              current_occupation: occ ? occ.code : "Other",
                            },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-amber-500/80 rounded p-1.5 text-xs text-amber-300 font-semibold focus:outline-none focus:border-amber-400"
                      >
                        {EVISA_DEFAULT_OCCUPATIONS.map((occ) => (
                          <option key={occ.id} value={occ.id}>
                            {occ.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Sub-dropdown & Custom Title if Other (ID: 1) or current_occupation === 'Other' */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1 border-t border-slate-800/80">
                      <div>
                        <span className="text-[10px] text-amber-300 font-semibold">Other Occupation Preset (Sub-dropdown)</span>
                        <select
                          value={
                            OTHER_OCCUPATION_PRESETS.includes(
                              extractedResult?.TravelDocument?.other_occupation || applicant.travelDoc.other_occupation || ""
                            )
                              ? extractedResult?.TravelDocument?.other_occupation || applicant.travelDoc.other_occupation
                              : "CUSTOM"
                          }
                          onChange={(e) => {
                            const val = e.target.value;
                            if (val !== "CUSTOM") {
                              setExtractedResult((prev: any) => ({
                                ...(prev || {}),
                                TravelDocument: {
                                  ...(prev?.TravelDocument || {}),
                                  other_occupation: val,
                                  current_occupation: "Other",
                                  occupation_id: "1",
                                },
                              }));
                            }
                          }}
                          className="w-full bg-slate-950 border border-amber-500 rounded p-1.5 text-xs text-amber-300 font-bold"
                        >
                          {OTHER_OCCUPATION_PRESETS.map((p) => (
                            <option key={p} value={p}>
                              {p}
                            </option>
                          ))}
                          <option value="CUSTOM">-- Custom Title --</option>
                        </select>
                      </div>

                      <div>
                        <span className="text-[10px] text-amber-300 font-semibold">Injected into #AltaOcupatie</span>
                        <input
                          type="text"
                          value={
                            extractedResult?.TravelDocument?.other_occupation ||
                            applicant.travelDoc.other_occupation ||
                            "FACTORY HELPER"
                          }
                          onChange={(e) => {
                            const val = e.target.value.toUpperCase();
                            setExtractedResult((prev: any) => ({
                              ...(prev || {}),
                              TravelDocument: {
                                ...(prev?.TravelDocument || {}),
                                other_occupation: val,
                                current_occupation: "Other",
                                occupation_id: "1",
                              },
                            }));
                          }}
                          className="w-full bg-slate-950 border border-amber-500 rounded p-1.5 text-xs text-amber-200 font-bold font-mono"
                        />
                      </div>
                    </div>
                  </div>
                </div>

                {/* 4. Spouse Details */}
                <div className="bg-slate-900/90 p-3.5 rounded-xl border border-pink-500/30 space-y-2.5">
                  <div className="flex items-center justify-between pb-1 border-b border-slate-800/80">
                    <span className="text-xs font-bold text-pink-300 flex items-center space-x-1.5">
                      <Heart className="w-3.5 h-3.5 text-pink-400" />
                      <span>Spouse Details (Marriage Certificate / ID Extraction)</span>
                    </span>
                    <span className="text-[10px] bg-pink-500/10 text-pink-300 border border-pink-500/20 px-2 py-0.5 rounded font-mono">
                      Spouse ID / Marriage Cert
                    </span>
                  </div>

                  {/* Spouse Surname & First Names */}
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-[10px] text-slate-400">Spouse Surname</span>
                      <input
                        type="text"
                        value={extractedResult?.SpouseData?.spouse_surname ?? applicant.spouseData.spouse_surname ?? ""}
                        onChange={(e) => {
                          const val = e.target.value;
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            APPLICANT_CIVIL_STATUS: val ? "Married" : (prev?.APPLICANT_CIVIL_STATUS || "Married"),
                            SpouseData: { ...(prev?.SpouseData || {}), spouse_surname: val },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono"
                      />
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-400">Spouse First Name</span>
                      <input
                        type="text"
                        value={
                          extractedResult?.SpouseData?.spouse_first_names ||
                          extractedResult?.SpouseData?.spouse_first_name ||
                          applicant.spouseData.spouse_first_names ||
                          (applicant.spouseData as any)?.spouse_first_name ||
                          ""
                        }
                        onChange={(e) => {
                          const val = e.target.value;
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            APPLICANT_CIVIL_STATUS: val ? "Married" : (prev?.APPLICANT_CIVIL_STATUS || "Married"),
                            SpouseData: { ...(prev?.SpouseData || {}), spouse_first_names: val, spouse_first_name: val },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono"
                      />
                    </div>
                  </div>

                  {/* Spouse Surname at Birth & DOB */}
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-[10px] text-slate-400">Spouse Surname at Birth</span>
                      <input
                        type="text"
                        value={
                          extractedResult?.SpouseData?.spouse_surname_at_birth ||
                          applicant.spouseData.spouse_surname_at_birth ||
                          extractedResult?.SpouseData?.spouse_surname ||
                          applicant.spouseData.spouse_surname ||
                          ""
                        }
                        onChange={(e) => {
                          const val = e.target.value;
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            APPLICANT_CIVIL_STATUS: val ? "Married" : (prev?.APPLICANT_CIVIL_STATUS || "Married"),
                            SpouseData: { ...(prev?.SpouseData || {}), spouse_surname_at_birth: val },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono"
                      />
                    </div>

                    <div>
                      <span className="text-[10px] text-slate-400">Spouse Date of Birth (DD / MM / YYYY)</span>
                      <div className="grid grid-cols-3 gap-1">
                        <input
                          type="text"
                          placeholder="DD"
                          value={
                            extractedResult?.SpouseData?.spouse_dob_day ||
                            applicant.spouseData.spouse_dob_day ||
                            (extractedResult?.SpouseData?.spouse_dob?.split(/[\/\-\.]/)[0]?.length <= 2 ? extractedResult?.SpouseData?.spouse_dob?.split(/[\/\-\.]/)[0] : "") ||
                            ""
                          }
                          onChange={(e) => {
                            const val = e.target.value;
                            setExtractedResult((prev: any) => ({
                              ...(prev || {}),
                              APPLICANT_CIVIL_STATUS: "Married",
                              SpouseData: { ...(prev?.SpouseData || {}), spouse_dob_day: val },
                            }));
                          }}
                          className="bg-slate-950 border border-slate-700 rounded p-1 text-xs text-slate-200 font-mono text-center"
                        />
                        <input
                          type="text"
                          placeholder="MM"
                          value={
                            extractedResult?.SpouseData?.spouse_dob_month ||
                            applicant.spouseData.spouse_dob_month ||
                            (extractedResult?.SpouseData?.spouse_dob?.split(/[\/\-\.]/)[1] || "")
                          }
                          onChange={(e) => {
                            const val = e.target.value;
                            setExtractedResult((prev: any) => ({
                              ...(prev || {}),
                              APPLICANT_CIVIL_STATUS: "Married",
                              SpouseData: { ...(prev?.SpouseData || {}), spouse_dob_month: val },
                            }));
                          }}
                          className="bg-slate-950 border border-slate-700 rounded p-1 text-xs text-slate-200 font-mono text-center"
                        />
                        <input
                          type="text"
                          placeholder="YYYY"
                          value={
                            extractedResult?.SpouseData?.spouse_dob_year ||
                            applicant.spouseData.spouse_dob_year ||
                            (extractedResult?.SpouseData?.spouse_dob?.split(/[\/\-\.]/)[2] || "")
                          }
                          onChange={(e) => {
                            const val = e.target.value;
                            setExtractedResult((prev: any) => ({
                              ...(prev || {}),
                              APPLICANT_CIVIL_STATUS: "Married",
                              SpouseData: { ...(prev?.SpouseData || {}), spouse_dob_year: val },
                            }));
                          }}
                          className="bg-slate-950 border border-slate-700 rounded p-1 text-xs text-slate-200 font-mono text-center"
                        />
                      </div>
                    </div>
                  </div>

                  {/* Spouse Country of Birth & Place of Birth */}
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-[10px] text-slate-400">Spouse Country of Birth</span>
                      <input
                        type="text"
                        value={extractedResult?.SpouseData?.spouse_country_of_birth ?? applicant.spouseData.spouse_country_of_birth ?? "Sri Lanka"}
                        onChange={(e) => {
                          const val = e.target.value;
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            APPLICANT_CIVIL_STATUS: "Married",
                            SpouseData: { ...(prev?.SpouseData || {}), spouse_country_of_birth: val },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono"
                      />
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-400">Spouse Place of Birth</span>
                      <input
                        type="text"
                        value={extractedResult?.SpouseData?.spouse_place_of_birth ?? applicant.spouseData.spouse_place_of_birth ?? "COLOMBO"}
                        onChange={(e) => {
                          const val = e.target.value;
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            APPLICANT_CIVIL_STATUS: "Married",
                            SpouseData: { ...(prev?.SpouseData || {}), spouse_place_of_birth: val },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono"
                      />
                    </div>
                  </div>
                </div>

                {/* 5. Applicant's Home Address Pipeline */}
                <div className="bg-slate-900/90 p-3.5 rounded-xl border border-blue-500/30 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-blue-400 flex items-center space-x-1.5">
                      <MapPin className="w-3.5 h-3.5" />
                      <span>Applicant's Home Address Pipeline</span>
                    </span>
                    <span className="text-[10px] bg-blue-500/10 text-blue-300 border border-blue-500/20 px-2 py-0.5 rounded font-mono">
                      Criminal Record / Police Report
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-[10px] text-slate-400">Home Country</span>
                      <input
                        type="text"
                        value={extractedResult?.AddressData?.home_country || applicant.addressData.home_country}
                        onChange={(e) => {
                          const val = e.target.value;
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            AddressData: { ...(prev?.AddressData || {}), home_country: val },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono"
                      />
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-400">Place / City</span>
                      <input
                        type="text"
                        value={extractedResult?.AddressData?.place || applicant.addressData.place}
                        onChange={(e) => {
                          const val = e.target.value;
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            AddressData: { ...(prev?.AddressData || {}), place: val },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono"
                      />
                    </div>
                  </div>

                  <div>
                    <span className="text-[10px] text-slate-400">Full Home Street Address</span>
                    <input
                      type="text"
                      value={extractedResult?.AddressData?.address || applicant.addressData.address}
                      onChange={(e) => {
                        const val = e.target.value;
                        setExtractedResult((prev: any) => ({
                          ...(prev || {}),
                          AddressData: { ...(prev?.AddressData || {}), address: val },
                        }));
                      }}
                      className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono"
                    />
                  </div>
                </div>

                {/* 6. Company Contact & Host Details */}
                <div className="bg-slate-900/90 p-3.5 rounded-xl border border-cyan-500/30 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-cyan-400 flex items-center space-x-1.5">
                      <Building2 className="w-3.5 h-3.5" />
                      <span>Company Contact & Host Details</span>
                    </span>
                    <div className="flex items-center space-x-2">
                      <button
                        type="button"
                        onClick={() => {
                          const cName = extractedResult?.CompanyContactData?.name ?? applicant.companyContactData.name;
                          const cAddr = extractedResult?.CompanyContactData?.full_address ?? applicant.companyContactData.full_address;
                          const cPhone = extractedResult?.CompanyContactData?.telephone_fax ?? applicant.companyContactData.telephone_fax;
                          const cEmail = extractedResult?.CompanyContactData?.email ?? applicant.companyContactData.email;
                          const cWp = extractedResult?.CompanyContactData?.work_permit_number ?? applicant.companyContactData.work_permit_number;
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            CompanyContactData: {
                              ...(prev?.CompanyContactData || {}),
                              name: cName,
                              full_address: cAddr,
                              telephone_fax: cPhone,
                              email: cEmail,
                              work_permit_number: cWp,
                            },
                            HostData: {
                              ...(prev?.HostData || {}),
                              type_of_host: prev?.HostData?.type_of_host || "Company",
                              hotel_name: cName,
                              host_address: cAddr,
                              host_phone: cPhone,
                              host_email: cEmail,
                            },
                            CostAndMeansData: {
                              ...(prev?.CostAndMeansData || {}),
                              host_name: cName,
                            },
                          }));
                        }}
                        className="text-[10px] bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 px-2 py-0.5 rounded font-mono transition-colors"
                        title="Sync company details into host pipeline fields"
                      >
                        ⚡ Sync Company &rarr; Host
                      </button>
                      <span className="text-[10px] bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 px-2 py-0.5 rounded font-mono">
                        Host Company & Stage 4
                      </span>
                    </div>
                  </div>

                  {/* Employer / Company Primary Details */}
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-[10px] text-slate-400">Employer / Host Company Name</span>
                      <input
                        type="text"
                        value={extractedResult?.CompanyContactData?.name ?? applicant.companyContactData.name}
                        onChange={(e) => {
                          const val = e.target.value;
                          setExtractedResult((prev: any) => {
                            const prevCompName = prev?.CompanyContactData?.name;
                            const prevHostName = prev?.HostData?.hotel_name;
                            const shouldSyncHost = !prevHostName || prevHostName === prevCompName;
                            return {
                              ...(prev || {}),
                              CompanyContactData: { ...(prev?.CompanyContactData || {}), name: val },
                              HostData: {
                                ...(prev?.HostData || {}),
                                hotel_name: shouldSyncHost ? val : prevHostName,
                              },
                              CostAndMeansData: {
                                ...(prev?.CostAndMeansData || {}),
                                host_name: shouldSyncHost ? val : (prev?.CostAndMeansData?.host_name || val),
                              },
                            };
                          });
                        }}
                        className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                      />
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-400">Work Permit Number (Aviz de munca)</span>
                      <input
                        type="text"
                        placeholder="e.g. WP-2026-991823"
                        value={extractedResult?.CompanyContactData?.work_permit_number ?? extractedResult?.PersonalData?.work_permit_number ?? applicant.companyContactData.work_permit_number}
                        onChange={(e) => {
                          const val = e.target.value;
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            CompanyContactData: { ...(prev?.CompanyContactData || {}), work_permit_number: val },
                            PersonalData: { ...(prev?.PersonalData || {}), work_permit_number: val },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-[10px] text-slate-400">Telephone / Fax (+40 Romanian)</span>
                      <input
                        type="text"
                        value={extractedResult?.CompanyContactData?.telephone_fax ?? applicant.companyContactData.telephone_fax}
                        onChange={(e) => {
                          const val = e.target.value;
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            CompanyContactData: { ...(prev?.CompanyContactData || {}), telephone_fax: val },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                      />
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-400">Company Email Address</span>
                      <input
                        type="text"
                        placeholder="e.g. office@company.ro"
                        value={extractedResult?.CompanyContactData?.email ?? applicant.companyContactData.email}
                        onChange={(e) => {
                          const val = e.target.value;
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            CompanyContactData: { ...(prev?.CompanyContactData || {}), email: val },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                      />
                    </div>
                  </div>

                  <div>
                    <span className="text-[10px] text-slate-400">Full Romanian Company Address</span>
                    <input
                      type="text"
                      value={extractedResult?.CompanyContactData?.full_address ?? applicant.companyContactData.full_address}
                      onChange={(e) => {
                        const val = e.target.value;
                        setExtractedResult((prev: any) => {
                          const prevCompAddr = prev?.CompanyContactData?.full_address;
                          const prevHostAddr = prev?.HostData?.host_address;
                          const shouldSyncHost = !prevHostAddr || prevHostAddr === prevCompAddr;
                          return {
                            ...(prev || {}),
                            CompanyContactData: { ...(prev?.CompanyContactData || {}), full_address: val },
                            HostData: {
                              ...(prev?.HostData || {}),
                              host_address: shouldSyncHost ? val : prevHostAddr,
                            },
                          };
                        });
                      }}
                      className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                    />
                  </div>

                  {/* Host Pipeline Sub-block */}
                  <div className="pt-2 border-t border-slate-800/80 space-y-2">
                    <div className="flex items-center justify-between text-[11px] font-semibold text-cyan-300">
                      <span className="flex items-center space-x-1">
                        <Building2 className="w-3 h-3 text-cyan-400" />
                        <span>Host Details (Stage 4 in E-Visa Automation)</span>
                      </span>
                    </div>

                    <div className="grid grid-cols-3 gap-2 text-xs">
                      <div>
                        <span className="text-[10px] text-slate-400">Type of Host</span>
                        <select
                          value={extractedResult?.HostData?.type_of_host || applicant.hostData.type_of_host || "Company"}
                          onChange={(e) => {
                            const val = e.target.value;
                            setExtractedResult((prev: any) => ({
                              ...(prev || {}),
                              HostData: { ...(prev?.HostData || {}), type_of_host: val },
                            }));
                          }}
                          className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                        >
                          <option value="Company">Company</option>
                          <option value="Hotel">Hotel</option>
                          <option value="Individual">Individual</option>
                          <option value="Other">Other</option>
                        </select>
                      </div>

                      <div className="col-span-2">
                        <span className="text-[10px] text-slate-400">Hotel / Host Name in Romania</span>
                        <input
                          type="text"
                          value={extractedResult?.HostData?.hotel_name || extractedResult?.CompanyContactData?.name || applicant.hostData.hotel_name}
                          onChange={(e) => {
                            const val = e.target.value;
                            setExtractedResult((prev: any) => ({
                              ...(prev || {}),
                              HostData: { ...(prev?.HostData || {}), hotel_name: val },
                              CostAndMeansData: { ...(prev?.CostAndMeansData || {}), host_name: val },
                            }));
                          }}
                          className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                        />
                      </div>
                    </div>

                    <div>
                      <span className="text-[10px] text-slate-400">Host Address in Romania</span>
                      <input
                        type="text"
                        value={extractedResult?.HostData?.host_address || extractedResult?.CompanyContactData?.full_address || applicant.hostData.host_address}
                        onChange={(e) => {
                          const val = e.target.value;
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            HostData: { ...(prev?.HostData || {}), host_address: val },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono focus:border-cyan-500 focus:outline-none"
                      />
                    </div>
                  </div>
                </div>

                {/* 7. Calculated Journey Dates & Insurance Valid Until */}
                <div className="bg-slate-900/90 p-3.5 rounded-xl border border-teal-500/30 space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-teal-400 flex items-center space-x-1.5">
                      <Calendar className="w-3.5 h-3.5 text-teal-400" />
                      <span>Calculated Journey Dates & Insurance Valid Until</span>
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        const calculated = calculateJourneyAndInsuranceDates();
                        setExtractedResult((prev: any) => ({
                          ...(prev || {}),
                          JourneyDetailsData: {
                            ...(prev?.JourneyDetailsData || {}),
                            arrival_date: calculated.arrival_date,
                            departure_date: calculated.departure_date,
                          },
                          CostAndMeansData: {
                            ...(prev?.CostAndMeansData || {}),
                            insurance_valid_until: calculated.insurance_valid_until,
                          },
                        }));
                      }}
                      className="flex items-center space-x-1 px-2 py-0.5 rounded bg-teal-500/10 hover:bg-teal-500/20 text-teal-300 border border-teal-500/30 text-[10px] font-mono transition-colors"
                      title="Re-calculate: Arrival = Today's Date of Next Month; Departure = 3 Months from Arrival; Insurance = 6 Months"
                    >
                      <RefreshCw className="w-3 h-3" />
                      <span>Auto-Calculate (Next Month + 3 Mos)</span>
                    </button>
                  </div>

                  <div className="grid grid-cols-3 gap-2 text-xs">
                    <div>
                      <div className="flex items-center justify-between mb-0.5">
                        <span className="text-[10px] text-slate-400">Arrival (MM/DD/YYYY)</span>
                        <span className="text-[9px] text-teal-400 font-mono">Next Mo. Today</span>
                      </div>
                      <input
                        type="text"
                        placeholder="MM/DD/YYYY"
                        value={extractedResult?.JourneyDetailsData?.arrival_date || applicant.journeyDetailsData.arrival_date}
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
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            JourneyDetailsData: {
                              ...(prev?.JourneyDetailsData || {}),
                              arrival_date: val,
                              ...(autoDep ? { departure_date: autoDep } : {}),
                            },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono focus:border-teal-500 focus:outline-none"
                      />
                    </div>
                    <div>
                      <div className="flex items-center justify-between mb-0.5">
                        <span className="text-[10px] text-slate-400">Departure (MM/DD/YYYY)</span>
                        <span className="text-[9px] text-teal-400 font-mono">+3 Months</span>
                      </div>
                      <input
                        type="text"
                        placeholder="MM/DD/YYYY"
                        value={extractedResult?.JourneyDetailsData?.departure_date || applicant.journeyDetailsData.departure_date}
                        onChange={(e) => {
                          const val = e.target.value;
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            JourneyDetailsData: { ...(prev?.JourneyDetailsData || {}), departure_date: val },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono focus:border-teal-500 focus:outline-none"
                      />
                    </div>
                    <div>
                      <div className="flex items-center justify-between mb-0.5">
                        <span className="text-[10px] text-slate-400">Insurance Expiry</span>
                        <span className="text-[9px] text-teal-400 font-mono">&ge; Stay End</span>
                      </div>
                      <input
                        type="text"
                        placeholder="MM/DD/YYYY"
                        value={extractedResult?.CostAndMeansData?.insurance_valid_until || applicant.costAndMeansData.insurance_valid_until}
                        onChange={(e) => {
                          const val = e.target.value;
                          setExtractedResult((prev: any) => ({
                            ...(prev || {}),
                            CostAndMeansData: { ...(prev?.CostAndMeansData || {}), insurance_valid_until: val },
                          }));
                        }}
                        className="w-full bg-slate-950 border border-slate-700 rounded p-1.5 text-xs text-slate-200 font-mono focus:border-teal-500 focus:outline-none"
                      />
                    </div>
                  </div>

                  <div className="p-2 rounded bg-slate-950/60 border border-slate-800 text-[10px] text-teal-400/90 font-mono flex items-center justify-between">
                    <span>⚡ Rule: Arrival = Today's date of next month ({calculateJourneyAndInsuranceDates().arrival_date}), Departure = 3 months from arrival ({calculateJourneyAndInsuranceDates().departure_date}).</span>
                  </div>
                </div>
              </div>
            ) : viewMode === "validation" ? (
              <div className="mt-3 space-y-3 max-h-[460px] overflow-y-auto pr-1">
                <div className="flex flex-wrap items-center justify-between gap-2 bg-slate-900/80 p-2.5 rounded-xl border border-slate-800 text-xs">
                  <div className="flex items-center space-x-1.5">
                    <Filter className="w-3.5 h-3.5 text-purple-400" />
                    <span className="font-semibold text-slate-300">Filter Audit:</span>
                    <button
                      onClick={() => setValidationFilter("all")}
                      className={`px-2 py-0.5 rounded font-bold text-[10px] transition-colors ${
                        validationFilter === "all" ? "bg-purple-600 text-white" : "bg-slate-800 text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      All ({validationSummary.totalFields})
                    </button>
                    <button
                      onClick={() => setValidationFilter("attention")}
                      className={`px-2 py-0.5 rounded font-bold text-[10px] transition-colors ${
                        validationFilter === "attention" ? "bg-amber-600 text-white" : "bg-slate-800 text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      Needs Review ({validationSummary.warningCount + validationSummary.errorCount})
                    </button>
                    <button
                      onClick={() => setValidationFilter("verified")}
                      className={`px-2 py-0.5 rounded font-bold text-[10px] transition-colors ${
                        validationFilter === "verified" ? "bg-emerald-600 text-white" : "bg-slate-800 text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      Verified ({validationSummary.verifiedCount})
                    </button>
                  </div>

                  <div className="flex items-center space-x-2">
                    <span className="text-[10px] text-emerald-400 font-mono font-bold bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-500/30">
                      Audit Score: {validationSummary.healthScore}% Match
                    </span>
                  </div>
                </div>

                {/* Validation Audit Cards Table */}
                <div className="space-y-2">
                  {validationSummary.results
                    .filter((r) => {
                      if (validationFilter === "attention") return r.status !== "verified";
                      if (validationFilter === "verified") return r.status === "verified";
                      return true;
                    })
                    .map((res) => (
                      <div
                        key={res.id}
                        className={`p-3 rounded-xl border transition-all ${
                          res.status === "verified"
                            ? "bg-slate-900/60 border-emerald-500/30"
                            : res.status === "warning"
                            ? "bg-amber-950/20 border-amber-500/40"
                            : "bg-rose-950/20 border-rose-500/40"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="space-y-1.5 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="text-xs font-bold text-slate-100">{res.label}</span>
                              {res.isCritical && (
                                <span className="text-[9px] bg-purple-500/20 text-purple-300 border border-purple-500/30 px-1.5 py-0.2 rounded font-mono">
                                  Critical Field
                                </span>
                              )}
                              {res.docSource && res.docSource !== "None" && (
                                <span className="text-[9px] bg-slate-800 text-cyan-300 border border-slate-700 px-1.5 py-0.2 rounded font-mono">
                                  Source: {res.docSource}
                                </span>
                              )}
                            </div>
                            <div className="text-xs font-mono font-bold text-cyan-300">
                              Extracted Value: {res.extractedValue || "<Unset / Empty>"}
                            </div>
                            <div className="text-[11px] text-slate-400 flex items-start space-x-1.5 mt-1">
                              <FileText className="w-3.5 h-3.5 text-slate-500 shrink-0 mt-0.5" />
                              <span className="italic font-mono bg-slate-950/80 px-2 py-0.5 rounded border border-slate-800 text-slate-300 break-all">
                                Doc Snippet: "{res.docExcerpt}"
                              </span>
                            </div>
                          </div>

                          <div className="flex flex-col items-end space-y-1 shrink-0">
                            <span
                              className={`px-2.5 py-1 rounded-lg text-[10px] font-bold font-mono flex items-center space-x-1 ${
                                res.status === "verified"
                                  ? res.exactMatch
                                    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                                    : "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                                  : res.status === "warning"
                                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                                  : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                              }`}
                            >
                              {res.status === "verified" ? (
                                <>
                                  <CheckCircle className="w-3.5 h-3.5" />
                                  <span>{res.exactMatch ? "Verbatim Match" : "Verified Match"}</span>
                                </>
                              ) : res.status === "warning" ? (
                                <>
                                  <AlertTriangle className="w-3.5 h-3.5" />
                                  <span>Format Review</span>
                                </>
                              ) : (
                                <>
                                  <XCircle className="w-3.5 h-3.5" />
                                  <span>Discrepancy</span>
                                </>
                              )}
                            </span>
                            <span className="text-[10px] text-slate-400 max-w-[150px] text-right">
                              {res.statusText}
                            </span>
                          </div>
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            ) : (
              <pre className="bg-slate-900 p-3.5 rounded-lg text-emerald-400 font-mono text-xs overflow-x-auto max-h-[440px] border border-slate-800 mt-3">
                {extractedResult
                  ? JSON.stringify(extractedResult, null, 2)
                  : JSON.stringify(
                      {
                        status: "No data extracted yet. Click 'Run Simultaneous AI Extraction'.",
                        activeCategory,
                      },
                      null,
                      2
                    )}
              </pre>
            )}
          </div>

          <div className="pt-3 border-t border-slate-800 flex items-center justify-between">
            <span className="text-xs text-slate-400">
              Extraction Status:{" "}
              <span className={extractedResult ? "text-emerald-400 font-bold" : "text-amber-400"}>
                {extractedResult ? "Ready for Master Pipeline" : "Awaiting Run"}
              </span>
            </span>
            {extractedResult && (
              <button
                onClick={handleApplyToState}
                className="text-xs text-cyan-400 font-bold hover:underline flex items-center space-x-1"
              >
                <span>Apply to Master State</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Local Python & Playwright Visa Automation Suite */}
      <div className="p-5 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 border border-emerald-500/30 rounded-2xl shadow-2xl space-y-5">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 pb-4 border-b border-slate-800">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 bg-emerald-500/10 text-emerald-400 rounded-xl border border-emerald-500/20">
              <Terminal className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
                <span>Local Python &amp; Playwright Visa Automation Suite</span>
                <span className="bg-emerald-500/20 text-emerald-300 text-[10px] px-2 py-0.5 rounded-full font-mono font-bold">
                  1-Click Windows Ready
                </span>
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Automatically injects all extracted schematics, local document folder paths, and photo upload coordinates into standalone Python + Playwright code.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={handlePreviewCode}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-xl border border-slate-700 transition-colors flex items-center space-x-1.5"
            >
              <Eye className="w-3.5 h-3.5 text-cyan-400" />
              <span>Preview Script</span>
            </button>

            <button
              onClick={() => triggerDownloadPythonScript()}
              disabled={isDownloadingScript}
              className="px-3.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-bold rounded-xl border border-slate-700 transition-all flex items-center space-x-1.5 active:scale-95"
            >
              {isDownloadingScript ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin text-cyan-400" />
              ) : (
                <Download className="w-3.5 h-3.5 text-cyan-400" />
              )}
              <span>.py Script</span>
            </button>

            <button
              onClick={() => triggerDownloadBatLauncher()}
              disabled={isDownloadingBat}
              className="px-3.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-amber-300 text-xs font-bold rounded-xl border border-amber-500/30 transition-all flex items-center space-x-1.5 active:scale-95"
            >
              {isDownloadingBat ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin text-amber-400" />
              ) : (
                <Terminal className="w-3.5 h-3.5 text-amber-400" />
              )}
              <span>⚡ .bat Launcher</span>
            </button>

            <button
              onClick={() => triggerDownloadZipPackage()}
              disabled={isDownloadingZip}
              className="px-4 py-1.5 bg-gradient-to-r from-emerald-600 via-teal-600 to-emerald-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-bold rounded-xl shadow-lg shadow-emerald-900/30 transition-all flex items-center space-x-2 active:scale-95"
            >
              {isDownloadingZip ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin text-white" />
                  <span>Packaging ZIP...</span>
                </>
              ) : (
                <>
                  <Package className="w-4 h-4 text-emerald-200" />
                  <span>📦 Download 1-Click Automation Package (.zip)</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Dual Input Controls: Documents Folder & Verification URL */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Supporting Documents & Photo Folder Path */}
          <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-800 space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-bold text-emerald-400 flex items-center space-x-1.5">
                <FolderOpen className="w-4 h-4" />
                <span>Supporting Documents &amp; Photo Folder Path (Local PC)</span>
              </label>
              <span className="text-[10px] text-slate-500 font-mono">Injected into Script</span>
            </div>
            <div className="flex items-center space-x-2">
              <div className="relative flex-1">
                <div className="absolute inset-y-0 left-0 pl-2.5 flex items-center pointer-events-none text-slate-500">
                  <HardDrive className="w-3.5 h-3.5" />
                </div>
                <input
                  type="text"
                  value={documentsFolderPath}
                  onChange={(e) => {
                    setDocumentsFolderPath(e.target.value);
                    onUpdateApplicant({
                      ...applicant,
                      documentsFolderPath: e.target.value,
                      photoUploadFolderPath: e.target.value,
                    });
                  }}
                  placeholder="e.g. C:/VisaDocs/"
                  className="w-full bg-slate-900 border border-slate-700 focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 rounded-lg pl-8 pr-2.5 py-1.5 text-xs text-emerald-300 font-mono shadow-inner"
                />
              </div>
              <div className="flex items-center space-x-1 shrink-0">
                <button
                  type="button"
                  onClick={() => {
                    setDocumentsFolderPath("C:/VisaDocs/");
                    onUpdateApplicant({
                      ...applicant,
                      documentsFolderPath: "C:/VisaDocs/",
                      photoUploadFolderPath: "C:/VisaDocs/",
                    });
                  }}
                  className="px-2 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] font-mono rounded border border-slate-700 transition-colors"
                >
                  C:/VisaDocs/
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setDocumentsFolderPath("./documents/");
                    onUpdateApplicant({
                      ...applicant,
                      documentsFolderPath: "./documents/",
                      photoUploadFolderPath: "./documents/",
                    });
                  }}
                  className="px-2 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] font-mono rounded border border-slate-700 transition-colors"
                >
                  ./documents/
                </button>
              </div>
            </div>
            <p className="text-[11px] text-slate-400 leading-tight">
              Auto-matches: <code className="text-emerald-400 font-mono">permit*.pdf</code>, <code className="text-emerald-400 font-mono">support*.pdf</code>, <code className="text-emerald-400 font-mono">criminal*.pdf</code>, <code className="text-emerald-400 font-mono">insurance*.pdf</code>, <code className="text-emerald-400 font-mono">passport*.pdf</code>, <code className="text-emerald-400 font-mono">photo*.jpg</code>
            </p>
          </div>

          {/* Romanian eVisa Portal Start / Verification URL */}
          <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-800 space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-bold text-cyan-400 flex items-center space-x-1.5">
                <Globe className="w-4 h-4" />
                <span>Portal Start / Verification Link URL</span>
              </label>
              <span className="text-[10px] text-slate-500 font-mono">Target Page</span>
            </div>
            <div className="flex items-center space-x-2">
              <div className="relative flex-1">
                <div className="absolute inset-y-0 left-0 pl-2.5 flex items-center pointer-events-none text-slate-500">
                  <ExternalLink className="w-3.5 h-3.5" />
                </div>
                <input
                  type="text"
                  value={startUrl}
                  onChange={(e) => {
                    setStartUrl(e.target.value);
                    onUpdateApplicant({
                      ...applicant,
                      verificationUrl: e.target.value,
                    });
                  }}
                  placeholder="https://eviza.mae.ro/home?lang=en"
                  className="w-full bg-slate-900 border border-slate-700 focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 rounded-lg pl-8 pr-2.5 py-1.5 text-xs text-cyan-300 font-mono shadow-inner"
                />
              </div>
              <button
                type="button"
                onClick={() => {
                  setStartUrl("https://eviza.mae.ro/home?lang=en");
                  onUpdateApplicant({
                    ...applicant,
                    verificationUrl: "https://eviza.mae.ro/home?lang=en",
                  });
                }}
                className="px-2 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] font-mono rounded border border-slate-700 transition-colors shrink-0"
              >
                Reset Default
              </button>
            </div>
            <p className="text-[11px] text-slate-400 leading-tight">
              Direct verification link or root portal link for automated file identification &amp; progression.
            </p>
          </div>
        </div>

        {/* Real-time Automation Field Ingestion Status Grid */}
        <div className="bg-slate-950/70 p-3 rounded-xl border border-slate-800">
          <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider block mb-2">
            Injected Automation Mapping Checklist
          </span>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            <div className="flex items-center space-x-2 bg-slate-900/90 p-2 rounded-lg border border-slate-800">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              <div className="truncate">
                <span className="text-[10px] text-slate-500 block">Applicant</span>
                <span className="text-slate-200 font-bold truncate block">
                  {extractedResult?.PersonalData?.first_names || applicant.personalData.first_names || "PERERA ANUSHKA"}
                </span>
              </div>
            </div>

            <div className="flex items-center space-x-2 bg-slate-900/90 p-2 rounded-lg border border-slate-800">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              <div className="truncate">
                <span className="text-[10px] text-slate-500 block">Occupation &amp; Alta</span>
                <span className="text-amber-300 font-bold truncate block font-mono">
                  {extractedResult?.TravelDocument?.other_occupation || applicant.travelDoc.other_occupation || "FACTORY HELPER"}
                </span>
              </div>
            </div>

            <div className="flex items-center space-x-2 bg-slate-900/90 p-2 rounded-lg border border-slate-800">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              <div className="truncate">
                <span className="text-[10px] text-slate-500 block">Company &amp; Permit</span>
                <span className="text-teal-300 font-bold truncate block">
                  {extractedResult?.CompanyContactData?.name || applicant.companyContactData.name || "RETEX GREEN SRL"}
                </span>
              </div>
            </div>

            <div className="flex items-center space-x-2 bg-slate-900/90 p-2 rounded-lg border border-slate-800">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              <div className="truncate">
                <span className="text-[10px] text-slate-500 block">Spouse &amp; Dates</span>
                <span className="text-purple-300 font-bold truncate block">
                  {extractedResult?.SpouseData?.spouse_first_name || applicant.spouseData.spouse_first_name || "SUNIL CHAMARA"}
                </span>
              </div>
            </div>

            <div className="flex items-center space-x-2 bg-slate-900/90 p-2 rounded-lg border border-slate-800">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              <div className="truncate">
                <span className="text-[10px] text-slate-500 block">Passport Dates</span>
                <span className="text-emerald-300 font-bold truncate block font-mono text-[11px]">
                  {extractedResult?.TravelDocument?.date_of_issue || applicant.travelDoc.date_of_issue || "—"} / {extractedResult?.TravelDocument?.valid_until || applicant.travelDoc.valid_until || "—"}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Code Preview Modal */}
      {showCodePreview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800 bg-slate-950">
              <div className="flex items-center space-x-2">
                <Terminal className="w-5 h-5 text-emerald-400" />
                <h3 className="text-sm font-bold text-slate-100 font-mono">
                  evisa_automation_playwright_{applicant.fileNumber || "script"}.py
                </h3>
              </div>
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(previewCode);
                    setCopiedCode(true);
                    setTimeout(() => setCopiedCode(false), 2000);
                  }}
                  className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-lg border border-slate-700 transition-colors flex items-center space-x-1.5"
                >
                  {copiedCode ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copiedCode ? "Copied!" : "Copy Code"}</span>
                </button>
                <button
                  onClick={handleDownloadPythonScript}
                  className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold rounded-lg transition-colors flex items-center space-x-1.5"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Download .py</span>
                </button>
                <button
                  onClick={() => setShowCodePreview(false)}
                  className="p-1.5 text-slate-400 hover:text-slate-100 rounded-lg hover:bg-slate-800 transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>
            <div className="p-4 overflow-y-auto flex-1 bg-slate-950 font-mono text-xs">
              <pre className="text-emerald-400 whitespace-pre overflow-x-auto selection:bg-emerald-800 selection:text-white">
                {previewCode}
              </pre>
            </div>
          </div>
        </div>
      )}

      {/* Validation Confirmation Gate Modal */}
      {showValidationGateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/85 backdrop-blur-md">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950">
              <div className="flex items-center space-x-3">
                <div className="p-2.5 bg-amber-500/10 text-amber-400 rounded-xl border border-amber-500/20">
                  <ShieldAlert className="w-5 h-5 animate-pulse" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-100 flex items-center space-x-2">
                    <span>Document Data Discrepancy &amp; Validation Checker</span>
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Verification Audit before appending extracted fields to automation script
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowValidationGateModal(false)}
                className="p-1.5 text-slate-400 hover:text-slate-100 rounded-lg hover:bg-slate-800 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-6 space-y-4 max-h-[60vh] overflow-y-auto">
              <div className="p-3.5 bg-amber-500/10 border border-amber-500/30 rounded-xl text-amber-200 text-xs flex items-start space-x-2.5">
                <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0 text-amber-400" />
                <div>
                  <p className="font-bold">Attention Needed Before Automation Script Generation:</p>
                  <p className="text-amber-300/80 mt-0.5">
                    The Validation Checker identified {validationSummary.errorCount + validationSummary.warningCount} field(s) that differ or require format verification against your uploaded document text.
                  </p>
                </div>
              </div>

              {/* List of Discrepancies */}
              <div className="space-y-2">
                <span className="text-xs font-bold text-slate-300 uppercase tracking-wider block">
                  Discrepancy Audit List ({validationSummary.results.filter((r) => r.status !== "verified").length} Items):
                </span>
                {validationSummary.results
                  .filter((r) => r.status !== "verified")
                  .map((res) => (
                    <div
                      key={res.id}
                      className={`p-3 rounded-xl border text-xs space-y-1 ${
                        res.status === "error"
                          ? "bg-rose-950/30 border-rose-500/40"
                          : "bg-amber-950/30 border-amber-500/40"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-slate-200">{res.label}</span>
                        <span
                          className={`px-2 py-0.5 rounded font-mono font-bold text-[10px] ${
                            res.status === "error"
                              ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                              : "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                          }`}
                        >
                          {res.statusText}
                        </span>
                      </div>
                      <div className="font-mono text-cyan-300 font-bold">
                        Extracted: {res.extractedValue || "<Empty / Missing>"}
                      </div>
                      <div className="text-[11px] text-slate-400 italic font-mono bg-slate-950/80 px-2 py-1 rounded border border-slate-800">
                        Doc Excerpt: "{res.docExcerpt}"
                      </div>
                    </div>
                  ))}
              </div>
            </div>

            {/* Modal Actions */}
            <div className="flex items-center justify-between px-6 py-4 bg-slate-950 border-t border-slate-800">
              <button
                onClick={() => {
                  setShowValidationGateModal(false);
                  setViewMode("validation");
                }}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-xl border border-slate-700 transition-colors"
              >
                Review in Audit Table
              </button>

              <div className="flex items-center space-x-2">
                <button
                  onClick={() => setShowValidationGateModal(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-bold rounded-xl transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => {
                    setShowValidationGateModal(false);
                    if (pendingScriptAction === "apply") handleApplyToState();
                    else if (pendingScriptAction === "py") handleDownloadPythonScript();
                    else if (pendingScriptAction === "bat") handleDownloadBatLauncher();
                    else if (pendingScriptAction === "zip") handleDownloadZipPackage();
                    setPendingScriptAction(null);
                  }}
                  className="px-5 py-2 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white text-xs font-bold rounded-xl shadow-lg shadow-emerald-900/30 transition-all flex items-center space-x-2"
                >
                  <Check className="w-4 h-4" />
                  <span>Confirm Data &amp; Generate Script</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
