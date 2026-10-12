import React, { useState } from "react";
import { Upload, FileCheck, AlertTriangle, CheckCircle2, ShieldAlert, Trash2, Code2, Copy, Check, Eye, X } from "lucide-react";
import { DocumentUploadItem, ApplicantRecord } from "../types";

interface SupportingDocsManagerProps {
  applicant: ApplicantRecord;
  onUpdateApplicant: (updated: ApplicantRecord) => void;
}

export const SupportingDocsManager: React.FC<SupportingDocsManagerProps> = ({
  applicant,
  onUpdateApplicant,
}) => {
  const documents = applicant.documents || [];
  const [selectedDocForBase64, setSelectedDocForBase64] = useState<DocumentUploadItem | null>(null);
  const [isManualBase64Open, setIsManualBase64Open] = useState<boolean>(false);
  const [manualDocId, setManualDocId] = useState<string>("");
  const [manualBase64Input, setManualBase64Input] = useState<string>("");
  const [manualFileName, setManualFileName] = useState<string>("");
  const [copiedDocId, setCopiedDocId] = useState<string | null>(null);

  const handleFileUpload = (docId: string, e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const fileSizeMb = +(file.size / (1024 * 1024)).toFixed(2);
    const hasNonLatin = /[^\x00-\x7F]/.test(file.name);

    let status: "uploaded" | "pending" | "error" = "uploaded";
    let errorMessage = "";

    if (fileSizeMb > 2.0) {
      status = "error";
      errorMessage = `File exceeds max 2MB limit (${fileSizeMb} MB)`;
    } else if (hasNonLatin) {
      status = "error";
      errorMessage = "Filename contains non-Latin characters";
    }

    const reader = new FileReader();
    reader.onload = () => {
      const fileDataUrl = reader.result as string;
      const updatedDocs = documents.map((doc) => {
        if (doc.id === docId) {
          return {
            ...doc,
            fileName: file.name,
            fileSizeMb,
            uploadedAt: new Date().toISOString().replace("T", " ").substring(0, 16),
            status,
            errorMessage,
            fileDataUrl,
          };
        }
        return doc;
      });

      onUpdateApplicant({
        ...applicant,
        documents: updatedDocs,
      });
    };
    reader.readAsDataURL(file);
  };

  const handleSaveManualBase64 = () => {
    if (!manualDocId || !manualBase64Input.trim()) return;

    let cleanBase64 = manualBase64Input.trim();
    let fileName = manualFileName.trim();

    if (!fileName) {
      const doc = documents.find((d) => d.id === manualDocId);
      fileName = doc ? `${doc.typeKey}.pdf` : "document.pdf";
    }

    // Ensure it has data URL scheme or raw base64
    let fileDataUrl = cleanBase64;
    if (!cleanBase64.startsWith("data:")) {
      const mime = fileName.toLowerCase().endsWith(".png")
        ? "image/png"
        : fileName.toLowerCase().endsWith(".jpg") || fileName.toLowerCase().endsWith(".jpeg")
        ? "image/jpeg"
        : "application/pdf";
      fileDataUrl = `data:${mime};base64,${cleanBase64}`;
    }

    // Estimate file size in MB from base64 length
    const approximateBytes = Math.round((cleanBase64.length * 3) / 4);
    const fileSizeMb = +(approximateBytes / (1024 * 1024)).toFixed(2);

    const updatedDocs = documents.map((doc) => {
      if (doc.id === manualDocId) {
        return {
          ...doc,
          fileName,
          fileSizeMb,
          uploadedAt: new Date().toISOString().replace("T", " ").substring(0, 16),
          status: "uploaded" as const,
          errorMessage: undefined,
          fileDataUrl,
        };
      }
      return doc;
    });

    onUpdateApplicant({
      ...applicant,
      documents: updatedDocs,
    });

    setIsManualBase64Open(false);
    setManualBase64Input("");
    setManualFileName("");
    setManualDocId("");
  };

  const handleRemoveFile = (docId: string) => {
    const updatedDocs = documents.map((doc) => {
      if (doc.id === docId) {
        return {
          ...doc,
          fileName: "Not Uploaded",
          fileSizeMb: 0,
          status: "pending" as const,
          errorMessage: undefined,
          fileDataUrl: undefined,
        };
      }
      return doc;
    });

    onUpdateApplicant({ ...applicant, documents: updatedDocs });
  };

  const handleCopyBase64 = (doc: DocumentUploadItem) => {
    if (!doc.fileDataUrl) return;
    navigator.clipboard.writeText(doc.fileDataUrl);
    setCopiedDocId(doc.id);
    setTimeout(() => setCopiedDocId(null), 2000);
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center space-x-2">
            <h2 className="text-lg font-bold text-slate-100">Supporting Documents Upload Pipeline</h2>
            <span className="text-xs font-mono px-2.5 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
              {documents.filter((d) => d.status === "uploaded").length} / {documents.length} Uploaded
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Portal constraints enforced: Maximum size 2MB per document | Latin characters only | Base64 File Encoding Active.
          </p>
        </div>

        <button
          onClick={() => {
            setManualDocId(documents[0]?.id || "");
            setIsManualBase64Open(true);
          }}
          className="inline-flex items-center space-x-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-cyan-400 text-xs font-semibold rounded-xl border border-slate-700 transition-all cursor-pointer shadow-sm"
        >
          <Code2 className="w-3.5 h-3.5" />
          <span>Paste Base64 Encoded Document</span>
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {documents.map((doc) => {
          const isUploaded = doc.status === "uploaded";
          const isError = doc.status === "error";
          const hasBase64 = !!doc.fileDataUrl;

          return (
            <div
              key={doc.id}
              className={`p-4 rounded-xl border transition-all ${
                isError
                  ? "bg-rose-950/20 border-rose-500/40"
                  : isUploaded
                  ? "bg-slate-950/80 border-emerald-500/30"
                  : "bg-slate-950/40 border-slate-800"
              }`}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center space-x-2">
                  <div
                    className={`p-2 rounded-lg ${
                      isUploaded
                        ? "bg-emerald-500/10 text-emerald-400"
                        : isError
                        ? "bg-rose-500/10 text-rose-400"
                        : "bg-slate-800 text-slate-400"
                    }`}
                  >
                    <FileCheck className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-xs font-bold text-slate-200">{doc.label}</h3>
                    <p className="text-[10px] font-mono text-cyan-400 mt-0.5">Required Code: {doc.requiredCode}</p>
                  </div>
                </div>

                <div className="flex items-center space-x-1.5">
                  {hasBase64 && (
                    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-cyan-950 text-cyan-300 border border-cyan-800/40">
                      Base64
                    </span>
                  )}
                  {isUploaded ? (
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      <CheckCircle2 className="w-3 h-3 mr-1" /> Ready
                    </span>
                  ) : isError ? (
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/10 text-rose-400 border border-rose-500/20">
                      <ShieldAlert className="w-3 h-3 mr-1" /> Error
                    </span>
                  ) : (
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                      Pending
                    </span>
                  )}
                </div>
              </div>

              <div className="bg-slate-900/90 p-3 rounded-lg border border-slate-800 text-xs font-mono mb-3">
                <div className="flex items-center justify-between text-slate-300">
                  <span className="truncate max-w-[180px]" title={doc.fileName}>
                    {doc.fileName}
                  </span>
                  {doc.fileSizeMb > 0 && <span className="text-slate-500 text-[10px]">{doc.fileSizeMb} MB</span>}
                </div>
                {hasBase64 && (
                  <p className="text-[10px] text-slate-500 font-mono mt-1 truncate">
                    Encoding: Base64 URI ({Math.round((doc.fileDataUrl?.length || 0) / 1024)} KB encoded)
                  </p>
                )}
                {doc.errorMessage && (
                  <p className="text-rose-400 text-[10px] mt-1.5 flex items-center">
                    <AlertTriangle className="w-3 h-3 mr-1 shrink-0" />
                    <span>{doc.errorMessage}</span>
                  </p>
                )}
              </div>

              <div className="flex items-center space-x-2">
                <label className="flex-1 inline-flex items-center justify-center space-x-1.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-lg cursor-pointer transition-colors border border-slate-700">
                  <Upload className="w-3.5 h-3.5 text-cyan-400" />
                  <span>{isUploaded ? "Replace File" : "Upload Document"}</span>
                  <input
                    type="file"
                    accept=".pdf,.jpg,.jpeg,.png,.bmp,.rtf"
                    onChange={(e) => handleFileUpload(doc.id, e)}
                    className="hidden"
                  />
                </label>

                {hasBase64 && (
                  <>
                    <button
                      onClick={() => setSelectedDocForBase64(doc)}
                      className="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg border border-slate-700 transition-colors"
                      title="Inspect Base64 Encoding"
                    >
                      <Eye className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleCopyBase64(doc)}
                      className="p-1.5 bg-slate-800 hover:bg-slate-700 text-cyan-400 rounded-lg border border-slate-700 transition-colors"
                      title="Copy Base64 Data URL"
                    >
                      {copiedDocId === doc.id ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
                    </button>
                  </>
                )}

                {isUploaded && (
                  <button
                    onClick={() => handleRemoveFile(doc.id)}
                    className="p-1.5 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 rounded-lg border border-rose-500/20 transition-colors"
                    title="Remove file"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Modal: Inspect Base64 Encoding */}
      {selectedDocForBase64 && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-5 shadow-2xl flex flex-col max-h-[85vh]">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center space-x-2">
                <Code2 className="w-5 h-5 text-cyan-400" />
                <h3 className="text-sm font-bold text-slate-100">
                  Base64 File Encoding: {selectedDocForBase64.label}
                </h3>
              </div>
              <button
                onClick={() => setSelectedDocForBase64(null)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="my-4 flex-1 overflow-hidden flex flex-col">
              <div className="flex items-center justify-between text-xs text-slate-400 font-mono mb-2">
                <span>File: {selectedDocForBase64.fileName}</span>
                <span>Length: {selectedDocForBase64.fileDataUrl?.length || 0} chars</span>
              </div>
              <textarea
                readOnly
                value={selectedDocForBase64.fileDataUrl || ""}
                className="w-full flex-1 min-h-[220px] bg-slate-950 border border-slate-800 rounded-xl p-3 text-[11px] font-mono text-cyan-300 resize-none focus:outline-none select-all"
              />
            </div>

            <div className="flex items-center justify-between pt-3 border-t border-slate-800">
              <button
                onClick={() => handleCopyBase64(selectedDocForBase64)}
                className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-bold rounded-xl transition-all flex items-center space-x-1.5 cursor-pointer shadow-md"
              >
                {copiedDocId === selectedDocForBase64.id ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                <span>{copiedDocId === selectedDocForBase64.id ? "Copied Base64!" : "Copy Base64 String"}</span>
              </button>

              <button
                onClick={() => setSelectedDocForBase64(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-bold rounded-xl transition-all cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Direct Base64 Paste & Upload */}
      {isManualBase64Open && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-5 shadow-2xl flex flex-col max-h-[85vh]">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center space-x-2">
                <Code2 className="w-5 h-5 text-cyan-400" />
                <h3 className="text-sm font-bold text-slate-100">Paste Base64 Encoded Document</h3>
              </div>
              <button
                onClick={() => setIsManualBase64Open(false)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-4 my-4 flex-1 overflow-y-auto">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Target Document Slot</label>
                <select
                  value={manualDocId}
                  onChange={(e) => setManualDocId(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
                >
                  {documents.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.label} ({d.requiredCode})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Document File Name</label>
                <input
                  type="text"
                  placeholder="e.g. WORK_PERMIT.pdf"
                  value={manualFileName}
                  onChange={(e) => setManualFileName(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">
                  Base64 String or Data URL (e.g. data:application/pdf;base64,JVBERi0x...)
                </label>
                <textarea
                  rows={6}
                  placeholder="Paste your raw Base64 string or data:application/pdf;base64,... here"
                  value={manualBase64Input}
                  onChange={(e) => setManualBase64Input(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs font-mono text-cyan-300 focus:outline-none focus:border-cyan-500"
                />
              </div>
            </div>

            <div className="flex items-center justify-end space-x-3 pt-3 border-t border-slate-800">
              <button
                onClick={() => setIsManualBase64Open(false)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-bold rounded-xl transition-all cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveManualBase64}
                disabled={!manualDocId || !manualBase64Input.trim()}
                className="px-4 py-2 bg-gradient-to-r from-cyan-600 to-teal-600 hover:from-cyan-500 hover:to-teal-500 disabled:opacity-40 text-white text-xs font-bold rounded-xl transition-all flex items-center space-x-1.5 cursor-pointer shadow-md"
              >
                <FileCheck className="w-4 h-4" />
                <span>Save Base64 Document</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

