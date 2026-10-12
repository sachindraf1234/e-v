export type TargetStageMode =
  | "FULL_PIPELINE"
  | "SELECT_VISA_TYPE"
  | "DIPLOMATIC_MISSION"
  | "VISA_PURPOSE"
  | "PARTICULAR_SITUATIONS"
  | "TERRITORIAL_JURISDICTION"
  | "PERSONAL_DATA"
  | "TRAVEL_DOCUMENT_OCCUPATION"
  | "APPLICANT_HOME_ADDRESS"
  | "HOST_DETAILS"
  | "COMPANY_CONTACT"
  | "DETAILS_ABOUT_VISA"
  | "COST_AND_MEANS"
  | "FAMILY_DETAILS"
  | "DETAILS_REGARDING_JOURNEY"
  | "PHOTO_UPLOAD"
  | "DOCUMENTS_UPLOAD"
  | "SUMMARY_FILE";

export interface SpouseData {
  spouse_surname: string;
  spouse_first_names: string;
  spouse_surname_at_birth: string;
  spouse_dob_day: string;
  spouse_dob_month: string;
  spouse_dob_year: string;
  spouse_country_of_birth: string;
  spouse_place_of_birth: string;
}

export interface FamilyData {
  father_surname: string;
  father_first_name: string;
  mother_surname: string;
  mother_first_name: string;
}

export interface HostData {
  type_of_host: "Hotel" | "Individual" | "Company" | "Other" | string;
  hotel_name: string;
  host_address: string;
  email?: string;
  host_email?: string;
  host_phone?: string;
}

export interface VisaRequestedDetails {
  main_destination: string;
  number_of_entries: "1" | "2" | "Multiple";
  duration_of_stay: string;
  previous_stays: string;
  means_of_transport: string;
}

export interface CompanyContactData {
  name: string;
  telephone_fax: string;
  full_address: string;
  email: string;
  work_permit_number: string;
}

export interface CostAndMeansData {
  cost_covered_by: "Myself" | "Host person(s)" | "Host company";
  host_name: string;
  means_cash: boolean;
  means_travellers_cheques: boolean;
  means_accommodation: boolean;
  means_credit_cards: boolean;
  means_insurance: boolean;
  insurance_valid_until: string;
  means_other: boolean;
}

export interface JourneyDetailsData {
  arrival_date: string;
  departure_date: string;
  first_entry_state: string;
  border_post: string;
  main_destination_state: string;
  planned_route: string;
}

export interface AddressData {
  home_country: string;
  place: string;
  address: string;
}

export interface PersonalData {
  surname: string;
  first_names: string;
  surname_at_birth: string;
  same_surname_at_birth: boolean;
  former_surnames: string;
  no_former_surnames: boolean;
  dob_day: string;
  dob_month: string;
  dob_year: string;
  country_of_birth: string;
  place_of_birth: string;
  country_of_residence: string;
  place_of_residence: string;
  current_nationality: string;
  nationality_at_birth: string;
  sex: "Male" | "Female" | "";
  marital_status: string;
  phone_number: string;
  work_permit_number?: string;
}

export interface TravelDocumentData {
  travel_document_type: string;
  passport_number: string;
  issuing_country: string;
  issuing_authority: string;
  date_of_issue: string;
  valid_until: string;
  residence_permission_return: "Yes" | "No" | "Residence is the same with the country of origin";
  current_occupation: string;
  occupation_id?: string;
  other_occupation: string;
  employer_name: string;
  employer_phone: string;
  employer_address: string;
}

export interface VisaApplicationSelection {
  visa_type: "Uniform visa" | "Long-stay visa";
  current_nationality: string;
  country_of_residence: string;
  diplomatic_mission: string;
  type_of_travel_document: string;
  is_biometric: "Yes" | "No";
  visa_purpose: string;
  particular_situation: string;
  territorial_jurisdiction: string;
}

export type DocumentTypeKey =
  | "WORK_PERMIT"
  | "MEANS_OF_SUPPORT"
  | "CRIMINAL_RECORD"
  | "TRAVEL_MEDICAL_INSURANCE"
  | "VALID_TRAVEL_DOCUMENT"
  | "PHOTOGRAPHS"
  | "OTHER_DOCUMENT";

export interface DocumentUploadItem {
  id: string;
  typeKey: DocumentTypeKey;
  label: string;
  requiredCode: string; // e.g. _MUN_1.pdf
  fileName: string;
  fileSizeMb: number;
  uploadedAt: string;
  status: "uploaded" | "pending" | "error";
  errorMessage?: string;
  fileDataUrl?: string;
}

export interface ApplicantRecord {
  id: string;
  fileNumber: string; // e.g. E25110721257414
  status: "Draft" | "Processing" | "Completed" | "Error";
  applicant_civil_status: "Married" | "Single" | "Divorced" | "Widowed" | "Separated";
  selection: VisaApplicationSelection;
  personalData: PersonalData;
  travelDoc: TravelDocumentData;
  familyData: FamilyData;
  spouseData: SpouseData;
  hostData: HostData;
  addressData: AddressData;
  visaRequestedDetails: VisaRequestedDetails;
  companyContactData: CompanyContactData;
  costAndMeansData: CostAndMeansData;
  journeyDetailsData: JourneyDetailsData;
  documents: DocumentUploadItem[];
  documentsFolderPath?: string; // Local folder path on applicant/user computer (e.g. C:/VisaDocs/)
  photoUploadFolderPath?: string;
  verificationUrl?: string;
  photoDataUrl?: string;
  aiExtractedData?: any;
  notes?: string;
  createdAt: string;
  updatedAt: string;
}

export interface AutomationConfig {
  targetMode: TargetStageMode;
  chromeHost: string;
  chromePort: number;
  documentsFolderPath?: string; // Local computer folder path for supporting documents
  elementWaitTimeoutSec: number;
  pageSaveTimeoutSec: number;
  crashDetectionEnabled: boolean;
  autoSaveEachStage: boolean;
  verboseLogging: boolean;
  browserHeadlessMode: boolean;
  targetApplicationUrl?: string;
  verificationLink?: string;
}

export interface AutomationLog {
  id: string;
  timestamp: string;
  stage: TargetStageMode | "SYSTEM" | "CONNECTIVITY";
  status: "info" | "success" | "warning" | "error";
  message: string;
  xpath?: string;
  codeSnippet?: string;
}

export interface ScriptGenerationParams {
  applicant: ApplicantRecord;
  config: AutomationConfig;
  customXpaths?: Record<string, string>;
}
