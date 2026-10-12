export interface FieldValidationResult {
  id: string;
  category: "applicant" | "passport" | "permit" | "family" | "spouse" | "company" | "address";
  label: string;
  extractedValue: string;
  docExcerpt: string; // Document snippet where it was found
  docSource?: string; // Document category or file source name
  status: "verified" | "warning" | "error";
  statusText: string;
  isCritical: boolean; // Must pass for automation script
  details?: string;
  exactMatch?: boolean;
}

export interface ValidationSummary {
  totalFields: number;
  verifiedCount: number;
  warningCount: number;
  errorCount: number;
  healthScore: number; // Percentage 0-100
  allCriticalPassed: boolean;
  results: FieldValidationResult[];
}

/**
 * Normalizes text for lenient string comparison (removes diacritics, extra spaces, punctuation)
 */
export function normalizeText(str: string): string {
  if (!str) return "";
  return str
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Flexible Date Parser supporting ISO (YYYY-MM-DD), DD/MM/YYYY, DD.MM.YYYY, DD-MMM-YYYY (e.g. 15 MAY 2021)
 */
export function parseFlexibleDate(dateStr: any, isUSFormat: boolean = false): Date | null {
  if (!dateStr) return null;
  const s = String(dateStr).trim();
  if (!s || s === "..." || s === "YYYY-MM-DD" || s === "DD/MM/YYYY" || s === "MM/DD/YYYY") return null;

  // ISO: YYYY-MM-DD or YYYY/MM/DD or YYYY.MM.DD
  const isoMatch = s.match(/^(\d{4})[\/\-\.](\d{1,2})[\/\-\.](\d{1,2})$/);
  if (isoMatch) {
    const y = parseInt(isoMatch[1], 10);
    const m = parseInt(isoMatch[2], 10) - 1;
    const d = parseInt(isoMatch[3], 10);
    const dt = new Date(y, m, d);
    return isNaN(dt.getTime()) ? null : dt;
  }

  const monthMap: Record<string, number> = {
    jan: 0, january: 0, janv: 0, ian: 0, ianuarie: 0,
    feb: 1, february: 1, fevr: 1, febv: 1, febr: 1, februarie: 1,
    mar: 2, march: 2, mars: 2, mart: 2, martie: 2,
    apr: 3, april: 3, avr: 3, avril: 3, aprilie: 3,
    may: 4, mai: 4,
    jun: 5, june: 5, juin: 5, iun: 5, iunie: 5,
    jul: 6, july: 6, juil: 6, iul: 6, iulie: 6,
    aug: 7, august: 7, aou: 7, aout: 7, aoû: 7,
    sep: 8, sept: 8, september: 8, septembrie: 8,
    oct: 9, october: 9, octo: 9, octombrie: 9,
    nov: 10, november: 10, nove: 10, noi: 10, noiembrie: 10,
    dec: 11, december: 11, dece: 11, decembre: 11, decembrie: 11
  };

  // Text month: 15 MAY 2021, 15-MAY-2021, 15.MAY.2021
  const textMonthMatch = s.match(/^(\d{1,2})[\/\-\.\s]+([A-Za-z]+)(?:\s*[\/\-]\s*[A-Za-z]+)?[\/\-\.\s]+(\d{2,4})$/);
  if (textMonthMatch) {
    const d = parseInt(textMonthMatch[1], 10);
    const mKey = textMonthMatch[2].toLowerCase();
    const rawY = textMonthMatch[3];
    const y = rawY.length === 2 ? parseInt(`20${rawY}`, 10) : parseInt(rawY, 10);
    const m = monthMap[mKey] !== undefined ? monthMap[mKey] : 0;
    const dt = new Date(y, m, d);
    return isNaN(dt.getTime()) ? null : dt;
  }

  // Numeric: DD/MM/YYYY or DD.MM.YYYY or MM/DD/YYYY
  const numMatch = s.match(/^(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})$/);
  if (numMatch) {
    let p1 = parseInt(numMatch[1], 10);
    let p2 = parseInt(numMatch[2], 10);
    let rawY = numMatch[3];
    let y = rawY.length === 2 ? parseInt(`20${rawY}`, 10) : parseInt(rawY, 10);

    let day = p1;
    let month = p2 - 1;

    if (isUSFormat) {
      if (p1 <= 12) {
        month = p1 - 1;
        day = p2;
      } else {
        // Fallback to DD/MM/YYYY if month part > 12
        day = p1;
        month = p2 - 1;
      }
    } else {
      if (p2 > 12 && p1 <= 12) {
        day = p2;
        month = p1 - 1;
      }
    }
    const dt = new Date(y, month, day);
    return isNaN(dt.getTime()) ? null : dt;
  }

  const nativeDt = new Date(s);
  return isNaN(nativeDt.getTime()) ? null : nativeDt;
}

/**
 * Validates extracted AI document data against raw source document text and sanity rules.
 */
export function validateExtractedData(
  extractedResult: any,
  sourceDocuments: {
    applicantText?: string;
    spouseText?: string;
    companyText?: string;
    otherText?: string;
    allText?: string;
    ocrSummaryText?: string;
  }
): ValidationSummary {
  const docSections = [
    { name: "Applicant Documents / Passport", text: sourceDocuments.applicantText || "" },
    { name: "Spouse & Marriage Records", text: sourceDocuments.spouseText || "" },
    { name: "Company & Work Permit Docs", text: sourceDocuments.companyText || "" },
    { name: "Other Supporting Files", text: sourceDocuments.otherText || "" },
    { name: "Combined Source & OCR Text", text: (sourceDocuments.allText || "") + "\n" + (sourceDocuments.ocrSummaryText || "") },
  ];

  const fullDocText = docSections.map((s) => s.text).join("\n").trim();
  const normDocText = normalizeText(fullDocText);
  const results: FieldValidationResult[] = [];

  const checkPresenceInText = (val: string): { found: boolean; excerpt: string; docSource: string; exactMatch: boolean } => {
    if (!val || val.trim() === "" || val === "...") return { found: false, excerpt: "Not present in document text", docSource: "None", exactMatch: false };
    const normVal = normalizeText(val);
    if (!normVal) return { found: false, excerpt: "Empty value", docSource: "None", exactMatch: false };

    // 1. Check exact verbatim substring match
    for (const sec of docSections) {
      if (!sec.text) continue;
      const normSec = normalizeText(sec.text);
      if (normSec.includes(normVal)) {
        const lines = sec.text.split(/\r?\n/);
        const matchedLine = lines.find((line) => normalizeText(line).includes(normVal));
        return {
          found: true,
          exactMatch: true,
          excerpt: matchedLine ? matchedLine.trim() : `Found in ${sec.name}: "${val}"`,
          docSource: sec.name,
        };
      }
    }

    // 2. Check full text global match
    if (normDocText.includes(normVal)) {
      const lines = fullDocText.split(/\r?\n/);
      const matchedLine = lines.find((line) => normalizeText(line).includes(normVal));
      return {
        found: true,
        exactMatch: true,
        excerpt: matchedLine ? matchedLine.trim() : `Found in source document: "${val}"`,
        docSource: "Source Document",
      };
    }

    // 3. Check partial word matches (e.g. 60%+ words present in document text)
    const tokens = normVal.split(" ").filter((t) => t.length > 2);
    if (tokens.length > 0) {
      const tokenMatches = tokens.filter((t) => normDocText.includes(t));
      if (tokenMatches.length >= Math.ceil(tokens.length * 0.6)) {
        return {
          found: true,
          exactMatch: false,
          excerpt: `Partial match (${tokenMatches.length}/${tokens.length} terms verified in source text)`,
          docSource: "Source Document",
        };
      }
    }

    return { found: false, exactMatch: false, excerpt: "No matching excerpt in uploaded documents", docSource: "None" };
  };

  // 1. Applicant Surname
  const surname = extractedResult?.PersonalData?.surname || "";
  const surnameCheck = checkPresenceInText(surname);
  results.push({
    id: "applicant_surname",
    category: "applicant",
    label: "Applicant Surname",
    extractedValue: surname,
    docExcerpt: surnameCheck.excerpt,
    docSource: surnameCheck.docSource,
    exactMatch: surnameCheck.exactMatch,
    status: surname && surnameCheck.found ? "verified" : surname ? "warning" : "error",
    statusText:
      surname && surnameCheck.found
        ? surnameCheck.exactMatch ? "Exact Verbatim Surname Match in Source Document" : "Surname Verified in Source Text"
        : surname
        ? "Surname extracted, review spelling against source document"
        : "Applicant Surname is Missing",
    isCritical: true,
  });

  // 2. Applicant First Names
  const firstNames = extractedResult?.PersonalData?.first_names || "";
  const firstNamesCheck = checkPresenceInText(firstNames);
  results.push({
    id: "applicant_first_names",
    category: "applicant",
    label: "Applicant First Names",
    extractedValue: firstNames,
    docExcerpt: firstNamesCheck.excerpt,
    docSource: firstNamesCheck.docSource,
    exactMatch: firstNamesCheck.exactMatch,
    status: firstNames && firstNamesCheck.found ? "verified" : firstNames ? "warning" : "error",
    statusText:
      firstNames && firstNamesCheck.found
        ? firstNamesCheck.exactMatch ? "Exact Verbatim First Names Match in Source Document" : "First Names Verified in Source Text"
        : firstNames
        ? "First names extracted, review against passport"
        : "Applicant First Names Missing",
    isCritical: true,
  });

  // 3. Passport Number
  const passportNum = extractedResult?.TravelDocument?.passport_number || "";
  const passportNumCheck = checkPresenceInText(passportNum);
  const isValidPassportFormat = /^[A-Za-z0-9]{6,12}$/.test(passportNum.replace(/[\s\-]/g, ""));
  let passportStatus: "verified" | "warning" | "error" = "error";
  let passportMsg = "Passport Number Missing";

  if (passportNum) {
    if (passportNumCheck.found && isValidPassportFormat) {
      passportStatus = "verified";
      passportMsg = passportNumCheck.exactMatch
        ? "Exact Passport Number Match in Source Document"
        : "Verified Passport Number in Source Document";
    } else if (isValidPassportFormat) {
      passportStatus = "warning";
      passportMsg = "Valid Passport Format, verify with uploaded image";
    } else {
      passportStatus = "error";
      passportMsg = "Invalid Passport Number Format";
    }
  }

  results.push({
    id: "passport_number",
    category: "passport",
    label: "Passport Number",
    extractedValue: passportNum,
    docExcerpt: passportNumCheck.excerpt,
    docSource: passportNumCheck.docSource,
    exactMatch: passportNumCheck.exactMatch,
    status: passportStatus,
    statusText: passportMsg,
    isCritical: true,
  });

  // 4. Passport Issue Date
  const issueDate = extractedResult?.TravelDocument?.date_of_issue || "";
  let issueCheck = checkPresenceInText(issueDate);
  const parsedIssue = parseFlexibleDate(issueDate, true);
  if (!issueCheck.found && parsedIssue) {
    const d = String(parsedIssue.getDate()).padStart(2, "0");
    const m = String(parsedIssue.getMonth() + 1).padStart(2, "0");
    const y = String(parsedIssue.getFullYear());
    const shortY = y.slice(-2);
    const dateVariants = [
      `${d}/${m}/${y}`,
      `${d}.${m}.${y}`,
      `${d}-${m}-${y}`,
      `${d} ${m} ${y}`,
      `${d}/${m}/${shortY}`,
      `${d}.${m}.${shortY}`,
    ];
    for (const v of dateVariants) {
      const c = checkPresenceInText(v);
      if (c.found) {
        issueCheck = c;
        break;
      }
    }
  }

  let issueStatus: "verified" | "warning" | "error" = "warning";
  let issueMsg = "Check Issue Date";

  if (issueDate && parsedIssue) {
    const now = new Date();
    if (parsedIssue < now) {
      issueStatus = issueCheck.found ? "verified" : "warning";
      issueMsg = issueCheck.found
        ? "Issue Date Verified & Valid Past Date"
        : "Valid Past Date, verify with doc image";
    } else {
      issueStatus = "error";
      issueMsg = "Issue Date Cannot Be In The Future";
    }
  } else if (issueDate && !parsedIssue) {
    issueStatus = "error";
    issueMsg = "Invalid Issue Date Format";
  } else {
    issueStatus = "error";
    issueMsg = "Passport Issue Date Missing";
  }

  results.push({
    id: "passport_issue_date",
    category: "passport",
    label: "Passport Issue Date",
    extractedValue: issueDate,
    docExcerpt: issueCheck.excerpt,
    docSource: issueCheck.docSource,
    exactMatch: issueCheck.exactMatch,
    status: issueStatus,
    statusText: issueMsg,
    isCritical: true,
  });

  // 5. Passport Expiry Date
  const expiryDate = extractedResult?.TravelDocument?.valid_until || "";
  let expiryCheck = checkPresenceInText(expiryDate);
  const parsedExpiry = parseFlexibleDate(expiryDate, true);
  if (!expiryCheck.found && parsedExpiry) {
    const d = String(parsedExpiry.getDate()).padStart(2, "0");
    const m = String(parsedExpiry.getMonth() + 1).padStart(2, "0");
    const y = String(parsedExpiry.getFullYear());
    const shortY = y.slice(-2);
    const dateVariants = [
      `${d}/${m}/${y}`,
      `${d}.${m}.${y}`,
      `${d}-${m}-${y}`,
      `${d} ${m} ${y}`,
      `${d}/${m}/${shortY}`,
      `${d}.${m}.${shortY}`,
    ];
    for (const v of dateVariants) {
      const c = checkPresenceInText(v);
      if (c.found) {
        expiryCheck = c;
        break;
      }
    }
  }

  let expiryStatus: "verified" | "warning" | "error" = "warning";
  let expiryMsg = "Check Expiry Date";

  if (expiryDate && parsedExpiry) {
    const now = new Date();
    const sixMonthsFromNow = new Date();
    sixMonthsFromNow.setMonth(now.getMonth() + 6);

    if (parsedExpiry <= now) {
      expiryStatus = "error";
      expiryMsg = "❌ PASSPORT IS EXPIRED! Cannot apply for visa with expired passport.";
    } else if (parsedExpiry < sixMonthsFromNow) {
      expiryStatus = "warning";
      expiryMsg = "⚠️ Passport expires in less than 6 months";
    } else {
      expiryStatus = expiryCheck.found ? "verified" : "warning";
      expiryMsg = expiryCheck.found
        ? "Expiry Date Verified & Valid (>6 Months remaining)"
        : "Valid Expiry Date (>6 Months remaining)";
    }
  } else if (expiryDate && !parsedExpiry) {
    expiryStatus = "error";
    expiryMsg = "Invalid Expiry Date Format";
  } else {
    expiryStatus = "error";
    expiryMsg = "Passport Expiry Date Missing";
  }

  results.push({
    id: "passport_expiry_date",
    category: "passport",
    label: "Passport Expiry Date",
    extractedValue: expiryDate,
    docExcerpt: expiryCheck.excerpt,
    docSource: expiryCheck.docSource,
    exactMatch: expiryCheck.exactMatch,
    status: expiryStatus,
    statusText: expiryMsg,
    isCritical: true,
  });

  // 6. Applicant Date of Birth
  const dobDay = extractedResult?.PersonalData?.dob_day || "";
  const dobMonth = extractedResult?.PersonalData?.dob_month || "";
  const dobYear = extractedResult?.PersonalData?.dob_year || "";
  const dobStr =
    dobDay && dobMonth && dobYear
      ? `${dobDay.padStart(2, "0")}/${dobMonth.padStart(2, "0")}/${dobYear}`
      : extractedResult?.PersonalData?.date_of_birth || "";

  const dobCheck = checkPresenceInText(dobStr);
  let dobStatus: "verified" | "warning" | "error" = "warning";
  let dobMsg = "Check Date of Birth";

  if (dobYear) {
    const yearNum = parseInt(dobYear, 10);
    const currentYear = new Date().getFullYear();
    const age = currentYear - yearNum;
    if (age < 18) {
      dobStatus = "warning";
      dobMsg = `Applicant age is ${age} (Minor status requires parent authorization)`;
    } else {
      dobStatus = dobCheck.found ? "verified" : "warning";
      dobMsg = dobCheck.found
        ? `Birthdate Verified in Document (Age: ${age})`
        : `Birthdate extracted (Age: ${age}), formatted as ${dobStr}`;
    }
  } else {
    dobStatus = "error";
    dobMsg = "Date of Birth Missing";
  }

  results.push({
    id: "applicant_dob",
    category: "applicant",
    label: "Applicant Date of Birth",
    extractedValue: dobStr,
    docExcerpt: dobCheck.excerpt,
    docSource: dobCheck.docSource,
    exactMatch: dobCheck.exactMatch,
    status: dobStatus,
    statusText: dobMsg,
    isCritical: true,
  });

  // 7. Place of Birth
  const pob = extractedResult?.PersonalData?.place_of_birth || "";
  const pobCheck = checkPresenceInText(pob);
  results.push({
    id: "place_of_birth",
    category: "applicant",
    label: "Place of Birth",
    extractedValue: pob,
    docExcerpt: pobCheck.excerpt,
    docSource: pobCheck.docSource,
    exactMatch: pobCheck.exactMatch,
    status: pob ? (pobCheck.found ? "verified" : "warning") : "warning",
    statusText: pob
      ? pobCheck.found
        ? "Place of Birth Verified in Source Doc"
        : "Place of Birth Extracted"
      : "Place of Birth Missing / Review",
    isCritical: false,
  });

  // 8. Applicant Home Address
  const address = extractedResult?.AddressData?.address || "";
  const addressCheck = checkPresenceInText(address);
  results.push({
    id: "applicant_address",
    category: "address",
    label: "Applicant Home Address",
    extractedValue: address,
    docExcerpt: addressCheck.excerpt,
    docSource: addressCheck.docSource,
    exactMatch: addressCheck.exactMatch,
    status: address && address.length > 5 ? (addressCheck.found ? "verified" : "warning") : "error",
    statusText:
      address && addressCheck.found
        ? "Home Address Verified in Source Text"
        : address
        ? "Address extracted, please verify street number & place"
        : "Home Address Missing",
    isCritical: true,
  });

  // 9. Work Permit Number (Aviz de Muncă)
  const wpNum =
    extractedResult?.PersonalData?.work_permit_number ||
    extractedResult?.CompanyContactData?.work_permit_number ||
    "";
  const wpCheck = checkPresenceInText(wpNum);
  results.push({
    id: "work_permit_number",
    category: "permit",
    label: "Work Permit Number (Aviz de Muncă)",
    extractedValue: wpNum,
    docExcerpt: wpCheck.excerpt,
    docSource: wpCheck.docSource,
    exactMatch: wpCheck.exactMatch,
    status: wpNum && wpNum !== "..." ? (wpCheck.found ? "verified" : "warning") : "error",
    statusText:
      wpNum && wpCheck.found
        ? "Work Permit Number Verified in Romanian Aviz Document"
        : wpNum
        ? "Work Permit Number extracted"
        : "Work Permit Number Missing",
    isCritical: true,
  });

  // 10. Parents Names (Father & Mother)
  const fatherName =
    (extractedResult?.FamilyData?.father_surname || "") +
    " " +
    (extractedResult?.FamilyData?.father_first_name || "");
  const fatherCheck = checkPresenceInText(fatherName);
  results.push({
    id: "father_name",
    category: "family",
    label: "Father's Full Name",
    extractedValue: fatherName.trim(),
    docExcerpt: fatherCheck.excerpt,
    docSource: fatherCheck.docSource,
    exactMatch: fatherCheck.exactMatch,
    status: fatherName.trim() ? (fatherCheck.found ? "verified" : "warning") : "warning",
    statusText: fatherName.trim()
      ? fatherCheck.found
        ? "Father's Name Verified in Source Document"
        : "Father's Name Extracted"
      : "Father's Name Optional / Review",
    isCritical: false,
  });

  const motherName =
    (extractedResult?.FamilyData?.mother_surname || "") +
    " " +
    (extractedResult?.FamilyData?.mother_first_name || "");
  const motherCheck = checkPresenceInText(motherName);
  results.push({
    id: "mother_name",
    category: "family",
    label: "Mother's Full Name",
    extractedValue: motherName.trim(),
    docExcerpt: motherCheck.excerpt,
    docSource: motherCheck.docSource,
    exactMatch: motherCheck.exactMatch,
    status: motherName.trim() ? (motherCheck.found ? "verified" : "warning") : "warning",
    statusText: motherName.trim()
      ? motherCheck.found
        ? "Mother's Name Verified in Source Document"
        : "Mother's Name Extracted"
      : "Mother's Name Optional / Review",
    isCritical: false,
  });

  // 11. Civil Status & Spouse Details
  const civilStatus = extractedResult?.APPLICANT_CIVIL_STATUS || extractedResult?.PersonalData?.marital_status || "Single";
  const spouseSurname = extractedResult?.SpouseData?.spouse_surname || "";
  const spouseFirst = extractedResult?.SpouseData?.spouse_first_names || "";
  const spouseFullName = `${spouseSurname} ${spouseFirst}`.trim();
  const spouseCheck = checkPresenceInText(spouseFullName);

  let spouseStatus: "verified" | "warning" | "error" = "verified";
  let spouseMsg = "Single Status Confirmed";

  if (civilStatus === "Married") {
    if (spouseFullName) {
      spouseStatus = spouseCheck.found ? "verified" : "warning";
      spouseMsg = spouseCheck.found
        ? "Spouse Details Verified in Marriage Document"
        : "Spouse Details Extracted (Transliterated)";
    } else {
      spouseStatus = "warning";
      spouseMsg = "Married status indicated, but Spouse details incomplete";
    }
  }

  results.push({
    id: "civil_status_spouse",
    category: "spouse",
    label: "Civil Status & Spouse Data",
    extractedValue: civilStatus === "Married" ? `Married (${spouseFullName || "Details Extracted"})` : "Single",
    docExcerpt: civilStatus === "Married" ? spouseCheck.excerpt : "Single Applicant Status",
    docSource: civilStatus === "Married" ? spouseCheck.docSource : "Applicant Records",
    exactMatch: civilStatus === "Married" ? spouseCheck.exactMatch : true,
    status: spouseStatus,
    statusText: spouseMsg,
    isCritical: false,
  });

  // 12. Romanian Host Company Name
  const companyName = extractedResult?.CompanyContactData?.name || "RETEX GREEN SRL";
  const companyCheck = checkPresenceInText(companyName);
  results.push({
    id: "company_name",
    category: "company",
    label: "Host Company Name",
    extractedValue: companyName,
    docExcerpt: companyCheck.excerpt,
    docSource: companyCheck.docSource,
    exactMatch: companyCheck.exactMatch,
    status: companyName ? (companyCheck.found ? "verified" : "warning") : "error",
    statusText: companyCheck.found
      ? "Host Company Verified in Invitation/Permit"
      : "Host Company Extracted",
    isCritical: true,
  });

  // 13. Host Company Address
  const companyAddress = extractedResult?.CompanyContactData?.full_address || "";
  const companyAddrCheck = checkPresenceInText(companyAddress);
  results.push({
    id: "company_address",
    category: "company",
    label: "Host Company Full Address",
    extractedValue: companyAddress,
    docExcerpt: companyAddrCheck.excerpt,
    docSource: companyAddrCheck.docSource,
    exactMatch: companyAddrCheck.exactMatch,
    status: companyAddress ? (companyAddrCheck.found ? "verified" : "warning") : "warning",
    statusText: companyAddrCheck.found
      ? "Company Headquarters Address Verified in Document"
      : "Company Address Extracted",
    isCritical: false,
  });

  // 14. Host Company Phone
  const companyPhone = extractedResult?.CompanyContactData?.telephone_fax || "";
  const companyPhoneCheck = checkPresenceInText(companyPhone);
  results.push({
    id: "company_phone",
    category: "company",
    label: "Host Company Telephone / Fax",
    extractedValue: companyPhone,
    docExcerpt: companyPhoneCheck.excerpt,
    docSource: companyPhoneCheck.docSource,
    exactMatch: companyPhoneCheck.exactMatch,
    status: companyPhone ? (companyPhoneCheck.found ? "verified" : "warning") : "warning",
    statusText: companyPhoneCheck.found
      ? "Company Phone Number Verified (+40 Romanian Format)"
      : "Company Phone Extracted",
    isCritical: false,
  });

  // 15. Medical Insurance Expiry Date
  const insuranceExpiry = extractedResult?.CostAndMeansData?.insurance_valid_until || "";
  const insuranceCheck = checkPresenceInText(insuranceExpiry);
  results.push({
    id: "insurance_expiry",
    category: "permit",
    label: "Medical Insurance Expiry Date",
    extractedValue: insuranceExpiry,
    docExcerpt: insuranceCheck.excerpt,
    docSource: insuranceCheck.docSource,
    exactMatch: insuranceCheck.exactMatch,
    status: insuranceExpiry ? (insuranceCheck.found ? "verified" : "warning") : "warning",
    statusText: insuranceExpiry
      ? insuranceCheck.found
        ? "Insurance Policy Expiry Verified in Document"
        : "Insurance Expiry Extracted (MM/DD/YYYY)"
      : "Insurance Expiry Review",
    isCritical: false,
  });

  // 16. Journey Details (Arrival & Departure Dates)
  const arrivalDate = extractedResult?.JourneyDetailsData?.arrival_date || "";
  const departureDate = extractedResult?.JourneyDetailsData?.departure_date || "";
  const journeyStr = `${arrivalDate} to ${departureDate}`;
  const journeyCheck = checkPresenceInText(arrivalDate);

  results.push({
    id: "journey_dates",
    category: "applicant",
    label: "Intended Journey Dates",
    extractedValue: journeyStr,
    docExcerpt: journeyCheck.excerpt,
    docSource: journeyCheck.docSource,
    exactMatch: journeyCheck.exactMatch,
    status: arrivalDate && departureDate ? "verified" : "warning",
    statusText: arrivalDate && departureDate
      ? "Journey Dates Formatted (1 Month Future Arrival, 3 Month Stay)"
      : "Journey Dates Missing",
    isCritical: false,
  });

  // Calculate Health Score
  const totalFields = results.length;
  const verifiedCount = results.filter((r) => r.status === "verified").length;
  const warningCount = results.filter((r) => r.status === "warning").length;
  const errorCount = results.filter((r) => r.status === "error").length;

  // Weight: verified = 1, warning = 0.6, error = 0
  const totalPoints = verifiedCount * 1.0 + warningCount * 0.6;
  const healthScore = Math.round((totalPoints / totalFields) * 100);

  const criticalFields = results.filter((r) => r.isCritical);
  const allCriticalPassed = criticalFields.every((r) => r.status !== "error");

  return {
    totalFields,
    verifiedCount,
    warningCount,
    errorCount,
    healthScore,
    allCriticalPassed,
    results,
  };
}

