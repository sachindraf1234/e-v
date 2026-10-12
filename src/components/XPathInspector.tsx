import React, { useState } from "react";
import { ShieldCheck, Code2, Edit3, Save, Check } from "lucide-react";

export const XPathInspector: React.FC = () => {
  const [xpaths, setXpaths] = useState({
    sessionExpiredCheck: "//*[contains(text(), 'Your session has expired')] | //*[contains(text(), 'Sesiunea dumneavoastră a expirat')]",
    currentNationalityPopout: "//li[contains(., 'Sri Lanka')] | //a[contains(., 'Sri Lanka')] | //*[contains(@class, 'rcbItem') and contains(., 'Sri Lanka')]",
    countryOfResidencePopout: "//li[contains(., 'Sri Lanka')] | //a[contains(., 'Sri Lanka')] | //*[contains(@class, 'rcbItem') and contains(., 'Sri Lanka')]",
    diplomaticMissionPopout: "//li[contains(., 'Colombo')] | //a[contains(., 'Colombo')] | //*[contains(@class, 'rcbItem') and contains(., 'Colombo')]",
    travelDocumentPopout: "//li[contains(., 'Ordinary')] | //li[contains(., 'Simplu')] | //*[contains(@class, 'rcbItem') and contains(., 'Ordinary')]",
    saveButton: "//button[contains(normalize-space(), 'Save')] | //*[contains(@class, 'btn') and contains(text(), 'Save')] | //a[contains(text(), 'Save')]",
    nextButton: "//button[contains(normalize-space(), 'Next')] | //*[contains(@class, 'btn') and contains(text(), 'Next')] | //a[contains(text(), 'Next')]",
    homeCountryDropdown: "//select[contains(@id, 'Home country') or contains(@name, 'Home country')] | //label[contains(., 'Home country')]/following-sibling::select",
    placeField: "//label[contains(., 'Place')]/following-sibling::input | //input[contains(@id, 'place')]",
    addressField: "//label[contains(., 'Address')]/following-sibling::textarea | //textarea[contains(@id, 'address')]",
    typeOfHostDropdown: "//select[contains(@id, 'Type of host')] | //label[contains(., 'Type of host')]/following-sibling::select",
    hotelNameField: "//label[contains(., 'Hotel name')]/following-sibling::input | //input[contains(@id, 'hotel_name')]",
    hostAddressField: "//label[contains(., 'Host address')]/following-sibling::textarea | //textarea[contains(@id, 'host_address')]",
    spouseSurnameField: "//label[contains(., 'Surname of spouse') and not(contains(., 'birth'))]/following-sibling::input",
    spouseFirstNameField: "//label[contains(., 'First name(s) of spouse')]/following-sibling::input",
    spouseBirthSurnameField: "//label[contains(., 'Surname of spouse at birth')]/following-sibling::input",
  });

  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
      <div className="flex items-center justify-between mb-6 pb-4 border-b border-slate-800">
        <div className="flex items-center space-x-3">
          <div className="p-3 bg-rose-500/10 text-rose-400 rounded-xl border border-rose-500/20">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-100">XPath Selectors & Session Guards Inspector</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Inspect and tune DOM element location strategies used by Selenium remote debugger connection.
            </p>
          </div>
        </div>

        <button
          onClick={handleSave}
          className="inline-flex items-center space-x-2 px-4 py-2 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-bold text-xs rounded-xl shadow-lg transition-all"
        >
          {saved ? <Check className="w-4 h-4 text-emerald-300" /> : <Save className="w-4 h-4" />}
          <span>{saved ? "Updated Selectors!" : "Save Strategy Changes"}</span>
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {Object.entries(xpaths).map(([key, value]) => (
          <div key={key} className="p-4 bg-slate-950 rounded-xl border border-slate-800">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider flex items-center space-x-1.5">
                <Code2 className="w-3.5 h-3.5" />
                <span>{key.replace(/([A-Z])/g, " $1")}</span>
              </span>
            </div>
            <textarea
              value={value}
              onChange={(e) => setXpaths({ ...xpaths, [key]: e.target.value })}
              rows={2}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-xs font-mono text-emerald-400 focus:border-cyan-500 focus:outline-none"
            />
          </div>
        ))}
      </div>
    </div>
  );
};
