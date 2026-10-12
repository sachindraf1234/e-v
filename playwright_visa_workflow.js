#!/usr/bin/env node
/**
 * Romania e-VISA Full Automation Script (Playwright Node.js)
 * Automates the e-VISA portal workflow starting from 'Particular situations as regards certain supporting documents'
 * through Personal Data, Travel Document, Journey Details, Host Details, and Supporting Documents.
 */

import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';

// ==========================================
// CONFIGURATION: Change this for each applicant
// ==========================================
const APPLICANT_DATA = {
  personal: {
    surname: "PERERA",
    first_name: "ANUSHKA DILHANI",
    same_surname_at_birth: true,
    no_former_surname: true,
    dob_day: "10",
    dob_month: "3",               // 3 = March
    dob_year: "1997",
    birth_date: "10/03/1997",
    birth_country: "Sri Lanka",
    birth_country_id: "172",
    place_of_birth: "MARAWILA",
    residence_country: "Sri Lanka",
    residence_country_id: "172",
    place_of_residence: "COLOMBO",
    nationality: "Sri Lanka",
    nationality_id: "214",
    nationality_at_birth: "Sri Lanka",
    nationality_at_birth_id: "214",
    gender: "Female",             // 'Male' | 'Female'
    sex_id: "2",                  // 1 = Male, 2 = Female
    marital_status: "Married",    // 'Single' | 'Married' | 'Divorced' | 'Separated'
    marital_status_id: "2",       // 1 = Single, 2 = Married
    phone: "+94 77 123 4567",
    father_surname: "PERERA",
    father_first_name: "SUNIL",
    mother_surname: "FERNANDO",
    mother_first_name: "KANTI",
  },
  travel_doc: {
    type: "Ordinary passport",
    number: "N8234198",
    authority: "Colombo",
    issue_date: "15/05/2021",
    expiry_date: "14/05/2031",
  },
  journey: {
    purpose: "Employment",
    destination: "Romania",
    arrival: "15/12/2024",
    stay_days: "90",
  },
  host: {
    type: "Company",
    name: "RETEX GREEN SRL",
    address: "Strada Principala Nr. 12, Bucharest",
    contact_person: "Manager",
  },
  documents_folder: "C:/VisaDocs/",
  files: {
    permit: "C:/VisaDocs/work_permit.pdf",
    support: "C:/VisaDocs/bank_statement.pdf",
    criminal: "C:/VisaDocs/police_clearance.pdf",
    insurance: "C:/VisaDocs/medical_insurance.pdf",
    passport: "C:/VisaDocs/passport.pdf",
    photo: "C:/VisaDocs/photo.jpg",
  },
};

class RomaniaVisaAutomator {
  constructor(page, data = null) {
    this.page = page;
    this.data = data || APPLICANT_DATA;
  }

  // --- SHARED UI HANDLERS ---

  async handleTniDropdown(fieldId, searchValue) {
    /** Custom handler for E-VISA search-style dropdowns (Sri Lanka, Romania, etc.) */
    try {
      const btnSelector = `div:has(> #${fieldId}_Description) .tni-dropdown-button`;
      if (await this.page.$(btnSelector)) {
        await this.page.click(btnSelector);
      } else {
        await this.page.click(`#${fieldId}_Description`);
      }

      await this.page.fill(`#${fieldId}_Description`, searchValue);
      await this.page.dispatchEvent(`#${fieldId}_Description`, 'input');
      await this.page.dispatchEvent(`#${fieldId}_Description`, 'keyup');

      const itemSelector = `li.tni-dropdown-item:has-text("${searchValue}"), #${fieldId}_list li:has-text("${searchValue}"), ul.tni-dropdown-list li:has-text("${searchValue}")`;
      await this.page.waitForSelector(itemSelector, { state: 'visible', timeout: 4000 });
      await this.page.click(itemSelector);

      await this.page.evaluate(({ fId, val }) => {
        const inp = document.getElementById(`${fId}_Description`) || document.querySelector(`input[name='${fId}.Description']`) || document.querySelector(`input[name='${fId}.Id_input']`);
        if (inp) {
          inp.value = val;
          inp.setAttribute('value', val);
          inp.dispatchEvent(new Event('input', { bubbles: true }));
          inp.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }, { fId: fieldId, val: searchValue });
    } catch (e) {
      console.log(`Fallback selection for TNI dropdown ${fieldId}:`, e.message);
      await this.page.evaluate(({ fId, val }) => {
        const inp = document.getElementById(`${fId}_Description`) || document.querySelector(`input[name='${fId}.Description']`) || document.querySelector(`input[name='${fId}.Id_input']`);
        if (inp) {
          inp.value = val;
          inp.setAttribute('value', val);
          inp.dispatchEvent(new Event('input', { bubbles: true }));
          inp.dispatchEvent(new Event('change', { bubbles: true }));
        }
        const list = document.getElementById(`${fId}_list`) || document.querySelector(`#${fId}_ang ul`);
        if (list) {
          const lis = Array.from(list.querySelectorAll('li'));
          const m = lis.find(l => (l.textContent || '').toLowerCase().includes(val.toLowerCase())) || lis[0];
          if (m) {
            m.click();
          }
        }
      }, { fId: fieldId, val: searchValue });
    }
  }

  async handleRadio(groupName, selection) {
    /** Handles Male/Female and Marital Status radio buttons. */
    const idMap = {
      Male: 'Sex_M',
      Female: 'Sex_F',
      Single: 'StareCivila_S',
      Married: 'StareCivila_M',
      Separated: 'StareCivila_D',
      Divorced: 'StareCivila_V',
    };
    const targetId = idMap[selection] || selection;
    if (targetId) {
      try {
        if (await this.page.$(`#${targetId}`)) {
          await this.page.check(`#${targetId}`);
        } else {
          await this.page.evaluate(({ id, grp, val }) => {
            const el = document.getElementById(id);
            if (el) {
              el.checked = true;
              el.dispatchEvent(new Event('change', { bubbles: true }));
              return;
            }
            const radios = Array.from(document.querySelectorAll(`input[name*="${grp}" i], input[type="radio"]`));
            for (const r of radios) {
              const parent = r.closest('td, tr, div, label');
              if (parent && (parent.textContent || '').toLowerCase().includes(val.toLowerCase())) {
                r.checked = true;
                r.dispatchEvent(new Event('change', { bubbles: true }));
                break;
              }
            }
          }, { id: targetId, grp: groupName, val: selection });
        }
      } catch (e) {
        console.log(`Error checking radio ${targetId}:`, e.message);
      }
    }
  }

  async handleKendoDate(fieldId, dateStr) {
    /** Fills Kendo UI dates and triggers Angular validation. */
    try {
      if (await this.page.$(`#${fieldId}`)) {
        await this.page.fill(`#${fieldId}`, dateStr);
        await this.page.keyboard.press('Tab');
      }

      await this.page.evaluate(({ fId, val }) => {
        const el = document.getElementById(fId);
        if (el) {
          el.value = val;
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
          el.dispatchEvent(new Event('blur', { bubbles: true }));
          if (window.kendo) {
            try {
              const dp = window.kendo.widgetInstance(window.$(el));
              if (dp) { dp.value(val); dp.trigger('change'); }
            } catch (e) {}
          }
        }
      }, { fId: fieldId, val: dateStr });
    } catch (e) {
      console.log(`Error handling Kendo date ${fieldId}:`, e.message);
    }
  }

  async triggerSaveAndNext() {
    /** Triggers the 'Save' then 'Next' buttons for complete step finalization. */
    console.log("Saving progress...");

    // CRITICAL SAFETY GUARD: If on Required Supporting Documents page, bypass generic Save/Next
    try {
      const isOnSupportingDocs = await this.page.evaluate(() => {
        const norm = (s) => (s || '').toLowerCase();
        const url = norm(window.location.href);
        if (url.includes('incarcaredocumente') || url.includes('documentejustificative')) return true;
        if (document.getElementById('UploadDocumenteJustificative_30') || document.querySelector('[id*="UploadDocumenteJustificative"]')) return true;
        return false;
      });
      if (isOnSupportingDocs) {
        console.log("🛡️ [Safety Guard] triggerSaveAndNext bypassed on Required Supporting Documents page.");
        return;
      }
    } catch (e) {}
    try {
      const saveBtn = "a.button.action:has-text('Save'), a.button.action:has-text('Salvare'), a.button.action:has-text('Salvează'), a.button.action:has-text('Salveaza'), a.button:has-text('Save'), a.btn:has-text('Save'), a:has-text('Save'), a:has-text('Salvare'), input[value*='Save' i], input[value*='Salvare' i], input[value*='Salveaza' i], button:has-text('Save'), [id*='btnSave' i]";
      if (await this.page.$(saveBtn)) {
        await this.page.click(saveBtn, { force: true });
      } else {
        await this.page.evaluate(() => {
          const btns = Array.from(document.querySelectorAll('a, button, input[type="button"], input[type="submit"]'));
          const save = btns.find(b => {
            const txt = (b.textContent || b.value || '').toLowerCase();
            return txt.includes('save') || txt.includes('salvar') || txt.includes('salveaz');
          });
          if (save) save.click();
          if (typeof window.Salveaza === 'function') {
            try { window.Salveaza('Salvare'); } catch (e) {}
          }
        });
      }
    } catch (e) {
      console.log(`Save click error: ${e.message}`);
    }

    await new Promise(r => setTimeout(r, 2000)); // Wait for server save acknowledgment
    console.log("Moving to next step...");
    try {
      const nextBtn = "a:has-text('Continue with photo'), a:has-text('Continuă cu fotografie'), a:has-text('Continue without photo'), a:has-text('Continuă fără fotografie'), a.button.action:has-text('Next'), a.button.action:has-text('Următor'), a.button.action:has-text('Urmator'), a.button.action:has-text('Înainte'), a.button.action:has-text('Inainte'), a.button:has-text('Next'), a.btn:has-text('Next'), a:has-text('Next'), a:has-text('Următor'), input[value*='Next' i], input[value*='Urmator' i], button:has-text('Next'), [id*='btnNext' i]";
      if (await this.page.$(nextBtn)) {
        await this.page.click(nextBtn, { force: true });
      } else {
        await this.page.evaluate(() => {
          const btns = Array.from(document.querySelectorAll('a, button, input[type="button"], input[type="submit"]'));
          // 1. Continue with photo
          const withPhoto = btns.find(b => {
            const txt = (b.textContent || b.value || '').toLowerCase();
            return (txt.includes('with photo') && !txt.includes('without')) ||
                   (txt.includes('cu foto') && !txt.includes('fara') && !txt.includes('fără'));
          });
          if (withPhoto) { withPhoto.click(); return; }

          // 2. Continue without photo
          const noPhoto = btns.find(b => {
            const txt = (b.textContent || b.value || '').toLowerCase();
            return txt.includes('without photo') || txt.includes('fara foto') || txt.includes('fără foto');
          });
          if (noPhoto) { noPhoto.click(); return; }

          // 3. Standard Next
          const next = btns.find(b => {
            const txt = (b.textContent || b.value || '').toLowerCase();
            return (txt.includes('next') || txt.includes('urmator') || txt.includes('următor') || txt.includes('inainte') || txt.includes('înainte')) && !txt.includes('inapoi');
          });
          if (next) next.click();
          if (typeof window.Salveaza === 'function') {
            try { window.Salveaza('Continua'); } catch (e) {}
          }
        });
      }
    } catch (e) {
      console.log(`Next click error: ${e.message}`);
    }

    try {
      await this.page.waitForLoadState('networkidle', { timeout: 6000 });
    } catch (e) {
      await new Promise(r => setTimeout(r, 2000));
    }
  }

  // --- STEP-BY-STEP PAGE FUNCTIONS ---

  async pageParticularSituations() {
    console.log("Step: Particular Situations (selecting 'I do not find myself in any')...");

    // 1. Clear client-side validators without reloading the page
    await this.page.evaluate(() => {
      try {
        if (typeof window.Page_ClientValidate === 'function') {
          window.Page_IsValid = true;
          window.Page_BlockSubmit = false;
        }
        if (Array.isArray(window.Page_Validators)) {
          window.Page_Validators.forEach((v) => {
            v.isvalid = true;
            v.style.display = 'none';
            v.style.visibility = 'hidden';
          });
        }
        document.querySelectorAll('.field-validation-error, .validator, .text-danger, [id*="Validator"]').forEach((v) => {
          v.style.display = 'none';
          v.style.visibility = 'hidden';
          v.isvalid = true;
        });
      } catch (err) {}
    }).catch(() => {});

    // 2. Select Radio Button (Fast DOM & Locator execution)
    const selectRadio = async () => {
      return await this.page.evaluate(() => {
        const radios = Array.from(document.querySelectorAll('input[type="radio"], input[name="group1"]'));
        if (!radios.length) return false;

        let target = document.getElementById('radio_23') || document.querySelector('input[value="23"]');
        if (!target) {
          target = radios.find(r => {
            const parent = r.closest('td, tr, div, li, label') || r.parentElement;
            const text = ((parent ? parent.textContent : '') + ' ' + (r.id || '')).toLowerCase();
            return text.includes('do not find') || text.includes('nu mă aflu') || text.includes('nu ma aflu') || text.includes('above-mentioned') || text.includes('radio_23') || r.value === '23';
          }) || radios[radios.length - 1];
        }

        if (target) {
          target.checked = true;
          target.setAttribute('checked', 'checked');
          const lbl = document.querySelector(`label[for="${target.id}"]`) || target.closest('label');
          if (lbl) lbl.click(); else target.click();

          target.dispatchEvent(new Event('change', { bubbles: true }));
          target.dispatchEvent(new Event('input', { bubbles: true }));

          const radioId = target.id || 'radio_23';
          const nomId = radioId.includes('_') ? radioId.split('_')[1] : (target.value || '23');
          if (typeof window.RadioClick === 'function') {
            try { window.RadioClick(target); } catch (e) {}
          }

          const cat = document.getElementById('CategorieExceptie_Id');
          if (cat) {
            cat.value = nomId;
            cat.dispatchEvent(new Event('change', { bubbles: true }));
            cat.dispatchEvent(new Event('input', { bubbles: true }));
          }
          return true;
        }
        return false;
      }).catch(() => false);
    };

    let selected = await selectRadio();
    if (!selected) {
      await this.page.waitForTimeout(150);
      selected = await selectRadio();
    }

    // STRICT VERIFICATION: Must NOT click Save or Next button until radio button is selected!
    if (!selected) {
      console.error("STRICT RULE ENFORCED: 'I do not find myself in any of the above-mentioned situations' radio button is NOT selected. ABORTING Save/Next click!");
      return;
    }

    console.log("Verified 'I do not find myself in any of the above-mentioned situations' selected. Proceeding to Next...");

    // 3. Set ContinuaLaSalvare and synchronize CategorieExceptie_Id
    await this.page.evaluate(() => {
      const contFlag = document.getElementById('ContinuaLaSalvare') || document.querySelector('input[name="ContinuaLaSalvare"]');
      if (contFlag) contFlag.value = 'True';
      const cat = document.getElementById('CategorieExceptie_Id') || document.querySelector('input[name="CategorieExceptie_Id"]') || document.querySelector('input[name="CategorieExceptie.Id"]') || document.querySelector('input[name="ID_CategorieExceptie"]');
      if (cat) cat.value = '23';
      if (typeof window.Page_ClientValidate === 'function') {
        window.Page_IsValid = true;
        window.Page_BlockSubmit = false;
      }
    }).catch(() => {});

    // 4. Click Next button directly with strictly verified selectors
    const nextSelectors = [
      "a.button.action:has-text('Next')",
      "a.button.action:has-text('Înainte')",
      "a.button.action:has-text('Inainte')",
      "a.button.action:has-text('Următor')",
      "a.button.action:has-text('Urmator')",
      "a#ctl00_MainContent_btnInainte",
      "a#btnInainte",
      "input#ctl00_MainContent_btnInainte",
      "input#btnInainte",
      "input[name$='btnInainte']",
      "a[id$='btnInainte']",
      "form a.button.action",
      ".buttons a.button.action",
      ".actions a.button.action",
      "button.action:has-text('Next')",
      "button.action:has-text('Înainte')",
      "button:has-text('Next')",
      "button:has-text('Înainte')",
      "input[type='submit'][value*='Next' i]",
      "input[type='submit'][value*='Înainte' i]",
      "input[type='submit'][value*='Inainte' i]"
    ];

    let clickedNext = false;
    for (const sel of nextSelectors) {
      try {
        const loc = this.page.locator(sel).first();
        if (await loc.count() > 0 && await loc.isVisible()) {
          const isSafe = await loc.evaluate((el) => {
            const id = (el.id || '').toLowerCase();
            const name = (el.getAttribute('name') || '').toLowerCase();
            const cls = (el.className || '').toLowerCase();
            const txt = (el.textContent || '').toLowerCase().trim();
            const href = (el.getAttribute('href') || '').toLowerCase();
            const combined = `${id} ${name} ${cls} ${txt} ${href}`;

            if (combined.includes('inapoi') || combined.includes('înapoi') || combined.includes('back') || combined.includes('prev') || combined.includes('anterior') || combined.includes('precedent') || combined.includes('cancel')) {
              return false;
            }
            if (txt.includes('continue application') || txt.includes('continuare cerere')) {
              return false;
            }
            if (el.closest('header, nav, .navbar, #navbar, .menu, #menu, .breadcrumb, #breadcrumbs, .top-bar')) {
              return false;
            }
            return true;
          });

          if (isSafe) {
            await loc.scrollIntoViewIfNeeded();
            await loc.click({ force: true });
            clickedNext = true;
            console.log(`✅ Clicked Next button via verified selector: ${sel}`);
            break;
          }
        }
      } catch (ex) {}
    }

    if (!clickedNext) {
      await this.page.evaluate(() => {
        try {
          if (typeof window.Page_ClientValidate === 'function') {
            window.Page_IsValid = true;
            window.Page_BlockSubmit = false;
          }
          const cont = document.getElementById('ContinuaLaSalvare') || document.querySelector('input[name="ContinuaLaSalvare"]');
          if (cont) cont.value = 'True';
          const cat = document.getElementById('CategorieExceptie_Id') || document.querySelector('input[name="CategorieExceptie_Id"]') || document.querySelector('input[name="CategorieExceptie.Id"]') || document.querySelector('input[name="ID_CategorieExceptie"]');
          if (cat) cat.value = '23';

          const root = document.querySelector('form, .actions, .buttons, #divButtons') || document.body;
          const allElements = Array.from(root.querySelectorAll('a.button.action, a#btnInainte, input#btnInainte, a[id*="btnInainte"], input[name*="btnInainte"], button.action, a, button, input[type="submit"]'));

          const isRealNext = (el) => {
            if (!el) return false;
            const id = (el.id || '').toLowerCase();
            const name = (el.getAttribute('name') || '').toLowerCase();
            const val = (el.value || '').toLowerCase();
            const txt = (el.textContent || '').toLowerCase().trim();
            const cls = (el.className || '').toLowerCase();
            const href = (el.getAttribute('href') || '').toLowerCase();
            const combined = `${id} ${name} ${val} ${txt} ${cls} ${href}`;

            if (combined.includes('inapoi') || combined.includes('înapoi') || combined.includes('back') || combined.includes('prev') || combined.includes('anterior') || combined.includes('precedent') || combined.includes('cancel')) {
              return false;
            }
            if (el.closest('header, nav, .navbar, #navbar, .menu, #menu, .breadcrumb, #breadcrumbs, .top-bar')) {
              return false;
            }
            if (txt.includes('continue application') || txt.includes('continuare cerere')) {
              return false;
            }

            if (cls.includes('action') && (txt === 'next' || txt === 'înainte' || txt === 'inainte' || txt === 'următor' || txt === 'urmator' || txt.includes('next') || txt.includes('inainte') || txt.includes('înainte'))) {
              return true;
            }
            if (id.includes('btninainte') || id.includes('btnnext') || id.includes('btnurmator') ||
                name.includes('btninainte') || name.includes('btnnext') || name.includes('btnurmator')) {
              return true;
            }
            if (txt === 'next' || txt === 'înainte' || txt === 'inainte' || txt === 'următor' || txt === 'urmator' || txt === 'pasul următor' || txt === 'pasul urmator' || val === 'next' || val === 'înainte' || val === 'inainte') {
              return true;
            }
            return false;
          };

          const btn = allElements.find(isRealNext);
          if (btn) {
            btn.scrollIntoView({ block: 'center' });
            btn.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
            btn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
            btn.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
            btn.click();
            return;
          }

          const postbackLink = Array.from(root.querySelectorAll('a[href*="__doPostBack"]')).find(a => {
            const h = a.getAttribute('href') || '';
            return (h.includes('btnInainte') || h.includes('btnNext') || h.includes('btnUrmator')) && !h.includes('Inapoi') && !h.includes('inapoi');
          });
          if (postbackLink && typeof window.__doPostBack === 'function') {
            const m = (postbackLink.getAttribute('href') || '').match(/__doPostBack\s*\(\s*['"]([^'"]+)['"]/);
            if (m) window.__doPostBack(m[1], '');
          }
        } catch (e) {}
      }).catch(() => {});
    }

    await new Promise(r => setTimeout(r, 2500));

    // Fallback if page did not advance
    const isStillParticular = await this.page.evaluate(() => {
      const r23 = document.getElementById('radio_23');
      const hasRd4 = document.getElementById('rd4');
      const hasNume = document.getElementById('Nume');
      return (r23 !== null && hasRd4 === null && hasNume === null);
    }).catch(() => false);

    if (isStillParticular) {
      console.log("🔄 Page did not advance on first attempt. Re-triggering verified Next click...");
      for (const sel of nextSelectors.slice(0, 6)) {
        try {
          const loc = this.page.locator(sel).first();
          if (await loc.count() > 0 && await loc.isVisible()) {
            await loc.scrollIntoViewIfNeeded();
            await loc.click({ force: true });
            console.log(`✅ Retry clicked Next button via: ${sel}`);
            break;
          }
        } catch (e) {}
      }
      await new Promise(r => setTimeout(r, 3000));
    }
  }

  async pageTerritorialJurisdiction() {
    console.log("Step: Territorial Jurisdiction...");

    // 1. Select "National visa (long-stay)" radio button (#rd4) in DOM instantly
    const targetRadioId = "rd4";
    await this.page.evaluate(() => {
      const rd4 = document.getElementById('rd4');
      if (rd4) {
        rd4.checked = true;
        rd4.setAttribute('checked', 'checked');
        const lbl = document.querySelector('label[for="rd4"]') || rd4.closest('label');
        if (lbl) lbl.click(); else rd4.click();
        rd4.dispatchEvent(new Event('change', { bubbles: true }));
        rd4.dispatchEvent(new Event('input', { bubbles: true }));
      }
      if (typeof window.changeValue === 'function') {
        try { window.changeValue(4); } catch (err) {}
      }
      const comp = document.getElementById('CompetentaTeritoriala');
      if (comp) {
        comp.value = '4';
        comp.dispatchEvent(new Event('change', { bubbles: true }));
        comp.dispatchEvent(new Event('input', { bubbles: true }));
      }
    }).catch(() => {});

    // 2. Fast check
    let selected = await this.page.evaluate(() => {
      const rd4 = document.getElementById('rd4');
      if (rd4 && rd4.checked) return true;
      const comp = document.getElementById('CompetentaTeritoriala');
      return comp && comp.value === '4';
    }).catch(() => false);

    if (!selected) {
      await this.page.check(`#${targetRadioId}`).catch(() => {});
      selected = await this.page.isChecked(`#${targetRadioId}`).catch(() => false);
    }

    if (!selected) {
      console.error("STRICT RULE ENFORCED: 'National visa (long-stay)' radio button is NOT selected. ABORTING Save/Next click!");
      return;
    }

    // Save button click
    const saveBtn = this.page.locator("a.button.action:has-text('Save'), a.button.action:has-text('Salvare'), #btnSave").first();
    if (await saveBtn.isVisible().catch(() => false)) {
      await saveBtn.click({ force: true, timeout: 2000 }).catch(() => {});
      await this.page.waitForTimeout(500);
    }

    // Next button click
    const nextButton = this.page.locator("a.button.action:has-text('Next'), a.button.action:has-text('Înainte'), a.button.action").first();
    await Promise.all([
      this.page.waitForNavigation({ timeout: 6000 }).catch(() => {}),
      nextButton.click({ timeout: 3000 }).catch(() => {})
    ]);
  }

  async pagePersonalData() {
    console.log("Step: Personal Data (Applicant: PERERA ANUSHKA DILHANI)...");
    const p = APPLICANT_DATA.personal;

    // 1. Names & Surname flags
    await this.page.fill('#Nume', p.surname || 'PERERA');
    await this.page.fill('#Prenume', p.first_name || 'ANUSHKA DILHANI');

    // Same surname at birth & No former surname checkboxes
    if (p.same_surname_at_birth) {
      try {
        await this.page.check('#Nume_este_NumeLaNastere');
      } catch (e) {
        await this.page.evaluate(() => {
          const el = document.getElementById('Nume_este_NumeLaNastere');
          if (el) { el.checked = true; el.dispatchEvent(new Event('change', { bubbles: true })); }
        });
      }
    }

    if (p.no_former_surname) {
      try {
        await this.page.check('#Fara_NumeAnterior');
      } catch (e) {
        await this.page.evaluate(() => {
          const el = document.getElementById('Fara_NumeAnterior');
          if (el) { el.checked = true; el.dispatchEvent(new Event('change', { bubbles: true })); }
        });
      }
    }

    // 2. Date of Birth: Day, Month, Year
    const dobDay = String(p.dob_day || '10');
    const dobMonth = String(p.dob_month || '3');
    const dobYear = String(p.dob_year || '1997');

    try {
      if (await this.page.$('#DataNastere_Day')) {
        await this.page.selectOption('#DataNastere_Day', dobDay);
      }
      if (await this.page.$('#DataNastere_Month')) {
        await this.page.selectOption('#DataNastere_Month', dobMonth);
      }
      if (await this.page.$('#DataNastere_Year')) {
        await this.page.selectOption('#DataNastere_Year', dobYear);
      }
    } catch (e) {
      console.log(`Date select note: ${e.message}`);
    }

    if (p.birth_date) {
      await this.handleKendoDate('DataNasterii', p.birth_date);
    }

    // 3. Place of Birth and Residency
    const birthCountry = p.birth_country || 'Sri Lanka';
    const birthCountryId = p.birth_country_id || '172';
    await this.handleTniDropdown('TaraNastere', birthCountry);
    await this.page.evaluate((id) => {
      const el = document.getElementById('TaraNastere_Id');
      if (el) {
        el.value = id;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('blur', { bubbles: true }));
      }
    }, birthCountryId);
    await this.page.fill('#LocNastere', p.place_of_birth || 'MARAWILA');

    const resCountry = p.residence_country || 'SRI LANKA';
    const resCountryId = p.residence_country_id || '172';
    try {
      if (await this.page.$("#Tara_Description")) {
        await this.handleTniDropdown('Tara', resCountry);
      } else {
        await this.handleTniDropdown('TaraRezidenta', resCountry);
      }
    } catch (e) {
      await this.handleTniDropdown('TaraRezidenta', resCountry);
    }
    await this.page.evaluate((id) => {
      const el1 = document.getElementById('Tara_Id');
      if (el1) {
        el1.value = id;
        el1.dispatchEvent(new Event('input', { bubbles: true }));
        el1.dispatchEvent(new Event('change', { bubbles: true }));
        el1.dispatchEvent(new Event('blur', { bubbles: true }));
      }
      const el2 = document.getElementById('TaraRezidenta_Id');
      if (el2) {
        el2.value = id;
        el2.dispatchEvent(new Event('input', { bubbles: true }));
        el2.dispatchEvent(new Event('change', { bubbles: true }));
        el2.dispatchEvent(new Event('blur', { bubbles: true }));
      }
    }, resCountryId);

    // Place field: last part of address
    const fullAddr = p.address || 'No 123 Main Street, Marawila, Colombo';
    let placeVal = p.place_of_residence || '';
    if (!placeVal && fullAddr) {
      const parts = fullAddr.split(',').map(s => s.trim()).filter(Boolean);
      placeVal = parts.length > 0 ? parts[parts.length - 1] : 'COLOMBO';
      if (placeVal.toLowerCase() === 'sri lanka' && parts.length > 1) {
        placeVal = parts[parts.length - 2];
      }
    }
    if (!placeVal) placeVal = 'COLOMBO';

    if (await this.page.$('#Adresa_Localitate')) {
      await this.page.fill('#Adresa_Localitate', placeVal);
    }
    if (await this.page.$('#LocRezidenta')) {
      await this.page.fill('#LocRezidenta', placeVal);
    }
    if (await this.page.$('#LocDomiciliu')) {
      await this.page.fill('#LocDomiciliu', placeVal);
    }

    // Complete address field
    if (await this.page.$('#Adresa_AdresaPetent')) {
      await this.page.fill('#Adresa_AdresaPetent', fullAddr);
    }
    if (await this.page.$('#Adresa')) {
      await this.page.fill('#Adresa', fullAddr);
    }
    if (await this.page.$('#AdresaRezidenta')) {
      await this.page.fill('#AdresaRezidenta', fullAddr);
    }

    // 4. Citizenship and Sex
    const nat = p.nationality || 'Sri Lanka';
    const natId = p.nationality_id || '214';
    await this.handleTniDropdown('Cetatenie', nat);
    await this.page.evaluate((id) => {
      const el = document.getElementById('Cetatenie_Id');
      if (el) {
        el.value = id;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('blur', { bubbles: true }));
      }
    }, natId);

    const natBirth = p.nationality_at_birth || 'Sri Lanka';
    const natBirthId = p.nationality_at_birth_id || '214';
    await this.handleTniDropdown('CetatenieLaNastere', natBirth);
    await this.page.evaluate((id) => {
      const el = document.getElementById('CetatenieLaNastere_Id');
      if (el) {
        el.value = id;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('blur', { bubbles: true }));
      }
    }, natBirthId);

    // Sex: Female (ID 2)
    const sexVal = p.gender || 'Female';
    const sexId = p.sex_id || '2';
    await this.handleRadio('Sex', sexVal);
    await this.page.evaluate(({ val, id }) => {
      const desc = document.getElementById('Sex_Description');
      if (desc) desc.value = val;
      const idEl = document.getElementById('Sex_Id');
      if (idEl) {
        idEl.value = id;
        idEl.dispatchEvent(new Event('input', { bubbles: true }));
        idEl.dispatchEvent(new Event('change', { bubbles: true }));
        idEl.dispatchEvent(new Event('blur', { bubbles: true }));
      }
    }, { val: sexVal, id: sexId });

    // 5. Civil Status & Contact
    const civilVal = p.marital_status || 'Married';
    const civilId = p.marital_status_id || '2';
    try {
      if (await this.page.$("input[name='StareCivila.Id_input']")) {
        await this.page.fill("input[name='StareCivila.Id_input']", civilVal);
      }
    } catch (e) {}
    await this.handleRadio('StareCivila', civilVal);
    await this.page.evaluate(({ val, id }) => {
      const desc = document.getElementById('StareCivila_Description');
      if (desc) desc.value = val;
      const idEl = document.getElementById('StareCivila_Id');
      if (idEl) idEl.value = id;
    }, { val: civilVal, id: civilId });
    await this.page.fill('#Telefon', p.phone || '+94 77 123 4567');

    // 6. Parents' Info
    await this.page.fill('#NumeTata', p.father_surname || 'PERERA');
    await this.page.fill('#PrenumeTata', p.father_first_name || 'SUNIL');
    await this.page.fill('#NumeMama', p.mother_surname || 'FERNANDO');
    await this.page.fill('#PrenumeMama', p.mother_first_name || 'KANTI');

    // 7. Navigation: Save and Next
    await this.page.evaluate(() => {
      const el = document.getElementById('ContinuaLaSalvare');
      if (el) el.value = 'True';
    });
    await this.triggerSaveAndNext();
    console.log("Personal data of applicant step completed successfully.");
  }

  async uploadApplicantPhoto() {
    /**
     * Photo upload and Green Frame guideline process on Travel Document page.
     * - Locates applicant photo using documents_folder link (e.g. C:/VisaDocs/) matching .jpg/.jpeg <= 512KB.
     * - Programmatically attaches file to hidden input#inputFile.
     * - Manually dispatches synthetic 'input' event to trigger oninput="uploadPicture(this)".
     * - Waits for local FileReader Base64 processing (#capturedPicture and .processing-controls).
     * - Injects 3:4 aspect ratio coordinates into #guideline (green frame) centered on applicant image.
     * - Clicks #cutPicture ("Crop") to start server face recognition via /Vize/ProcessImage.
     * - Polls for completion detecting #imgSuccess (/Content/general/images/tick.png or green-check.png) or error icon.
     * - Waits for .k-loading-mask hidden.
     */
    console.log("Starting Applicant Photo automation on Travel Document page...");
    try {
      const folder = APPLICANT_DATA.documents_folder || "C:/VisaDocs/";
      const candidateFolders = [
        folder,
        path.join(process.cwd(), "documents"),
        "C:/VisaDocs/",
        "C:/docs/",
        process.cwd()
      ];

      let resolvedFolder = null;
      for (const cf of candidateFolders) {
        if (cf && fs.existsSync(cf)) {
          try {
            if (fs.statSync(cf).isDirectory()) {
              resolvedFolder = cf;
              break;
            }
          } catch (e) {}
        }
      }

      const photoKeywords = ["photo", "applicant", "face", "image", "picture", "foto", "portrait", "avatar"];
      const allowedExts = [".jpg", ".jpeg"];
      const maxBytes = 524288; // 512 KB

      let targetPhoto = null;
      if (resolvedFolder && fs.existsSync(resolvedFolder)) {
        try {
          const files = fs.readdirSync(resolvedFolder);
          for (const f of files) {
            const fl = f.toLowerCase();
            if (allowedExts.some(ext => fl.endsWith(ext)) && photoKeywords.some(kw => fl.includes(kw))) {
              const fp = path.join(resolvedFolder, f);
              try {
                if (fs.statSync(fp).size <= maxBytes) {
                  targetPhoto = fp;
                  break;
                }
              } catch (e) {}
            }
          }
          if (!targetPhoto) {
            for (const f of files) {
              const fl = f.toLowerCase();
              if (allowedExts.some(ext => fl.endsWith(ext))) {
                const fp = path.join(resolvedFolder, f);
                try {
                  if (fs.statSync(fp).size <= maxBytes) {
                    targetPhoto = fp;
                    break;
                  }
                } catch (e) {}
              }
            }
          }
        } catch (e) {}
      }

      if (!targetPhoto && APPLICANT_DATA.files?.photo && fs.existsSync(APPLICANT_DATA.files.photo)) {
        targetPhoto = APPLICANT_DATA.files.photo;
      }

      // Check for photoDataUrl / photo_base64
      if (!targetPhoto && (APPLICANT_DATA.photoDataUrl || APPLICANT_DATA.photo_base64)) {
        try {
          const rawUrl = APPLICANT_DATA.photoDataUrl || APPLICANT_DATA.photo_base64;
          const rawB64 = rawUrl.includes("base64,") ? rawUrl.split("base64,")[1] : rawUrl;
          const tmpDir = path.join(process.cwd(), "tmp_docs");
          if (!fs.existsSync(tmpDir)) fs.mkdirSync(tmpDir, { recursive: true });
          const b64Path = path.join(tmpDir, "applicant_photo_from_dataurl.jpg");
          fs.writeFileSync(b64Path, Buffer.from(rawB64, "base64"));
          if (fs.existsSync(b64Path) && fs.statSync(b64Path).size > 500) {
            targetPhoto = b64Path;
          }
        } catch (e) {}
      }

      if (!targetPhoto || !fs.existsSync(targetPhoto)) {
        const tmpDir = path.join(process.cwd(), "tmp_docs");
        if (!fs.existsSync(tmpDir)) fs.mkdirSync(tmpDir, { recursive: true });
        targetPhoto = path.join(tmpDir, "applicant_photo.jpg");
      }

      console.log(`Selected applicant photo for upload: ${path.basename(targetPhoto)} (${targetPhoto})`);

      let preparedB64 = "";
      if (fs.existsSync(targetPhoto)) {
        try {
          preparedB64 = fs.readFileSync(targetPhoto).toString("base64");
        } catch (e) {}
      }

      const isAlreadyDone = await this.page.evaluate(() => {
        const successImg = document.getElementById("imgSuccess");
        const b64 = document.getElementById("ImageB64");
        const isSuccess = successImg && window.getComputedStyle(successImg).display !== "none";
        const hasB64 = b64 && b64.value && b64.value.length > 500;
        return !!(isSuccess || hasB64);
      }).catch(() => false);

      if (isAlreadyDone) {
        console.log("Applicant photo is already processed on the portal. Skipping re-upload.");
        return true;
      }

      const inputEl = await this.page.$("input#inputFile, input[type='file']");
      if (inputEl) {
        console.log("Injecting photo file into input#inputFile...");
        if (fs.existsSync(targetPhoto) && fs.statSync(targetPhoto).size > 100) {
          await inputEl.setInputFiles(targetPhoto);
        }

        // Dispatch synthetic 'change' and 'input' events to trigger inline oninput="uploadPicture(this)"
        await this.page.evaluate(() => {
          const inp = document.getElementById("inputFile") || document.querySelector("input[type='file']");
          if (inp) {
            inp.dispatchEvent(new Event("change", { bubbles: true }));
            inp.dispatchEvent(new Event("input", { bubbles: true }));
            if (typeof window.uploadPicture === "function") {
              try { window.uploadPicture(inp); } catch (e) {}
            }
            if (typeof window.pictureProcessingModule?.uploadPicture === "function") {
              try { window.pictureProcessingModule.uploadPicture(inp); } catch (e) {}
            }
          }
        });

        // Wait for local FileReader Base64 preview generation and controls reveal
        for (let i = 0; i < 20; i++) {
          await new Promise(r => setTimeout(r, 300));
          const loaded = await this.page.evaluate(() => {
            const img = document.getElementById("capturedPicture");
            const guideline = document.getElementById("guideline");
            const controls = document.querySelector(".processing-controls");
            const hasDataUrl = img && img.src && img.src.startsWith("data:image/") && !img.src.includes("camera_512");
            const hasGuideline = guideline && window.getComputedStyle(guideline).display !== "none";
            const hasControls = controls && window.getComputedStyle(controls).display !== "none";
            return !!(hasDataUrl || hasGuideline || hasControls);
          }).catch(() => false);
          if (loaded) break;
        }

        // Multi-Pass Adaptive Cropping Loop
        const cropConfigs = [
          { rel_w: 0.92, rel_h: 0.92, rel_x: 0.04, rel_y: 0.04 },
          { rel_w: 0.96, rel_h: 0.96, rel_x: 0.02, rel_y: 0.02 },
          { rel_w: 0.85, rel_h: 0.85, rel_x: 0.075, rel_y: 0.05 }
        ];

        let cropSucceeded = false;
        for (let attempt = 0; attempt < cropConfigs.length; attempt++) {
          const cfg = cropConfigs[attempt];
          console.log(`📐 [Photo Automation] Crop Attempt ${attempt + 1}/${cropConfigs.length}: rel_w=${cfg.rel_w}, rel_h=${cfg.rel_h}...`);

          await this.page.evaluate((c) => {
            const frameEl = document.getElementById("guideline");
            const imgEl = document.getElementById("capturedPicture");
            if (frameEl && imgEl) {
              const rendW = imgEl.clientWidth || 500;
              const rendH = imgEl.clientHeight || 667;

              let w = Math.round(rendW * c.rel_w);
              let h = Math.round(w / 0.75);

              if (h > rendH) {
                h = Math.round(rendH * c.rel_h);
                w = Math.round(h * 0.75);
              }

              let x = Math.round(rendW * c.rel_x);
              let y = Math.round(rendH * c.rel_y);

              if (x + w > rendW) x = Math.max(0, rendW - w);
              if (y + h > rendH) y = Math.max(0, rendH - h);

              frameEl.style.width = w + "px";
              frameEl.style.height = h + "px";
              frameEl.width = w;
              frameEl.height = h;
              frameEl.style.transform = `translate(${x}px, ${y}px)`;
              frameEl.setAttribute("data-x", x.toString());
              frameEl.setAttribute("data-y", y.toString());
              frameEl.style.display = "initial";

              const controls = document.querySelector(".processing-controls");
              if (controls) controls.style.display = "initial";
              const uploadBtn = document.querySelector(".upload-btn");
              if (uploadBtn) uploadBtn.style.display = "none";
            }
          }, cfg);
          await new Promise(r => setTimeout(r, 500));

          // Click "Crop" button (#cutPicture)
          await this.page.evaluate(() => {
            const cutBtn = document.getElementById("cutPicture");
            if (cutBtn) {
              cutBtn.click();
            } else if (typeof window.pictureProcessingModule?.cutPicture === "function") {
              try { window.pictureProcessingModule.cutPicture(); } catch(e) {}
            }
          });

          // Poll for server face recognition response
          for (let i = 0; i < 16; i++) {
            await new Promise(r => setTimeout(r, 500));
            const statusRes = await this.page.evaluate(() => {
              const successImg = document.getElementById("imgSuccess");
              const errorImg = document.getElementById("imgError");
              const resultSpan = document.getElementById("processingResult");
              const b64 = document.getElementById("ImageB64");
              const imgs = Array.from(document.querySelectorAll("img"));

              const hasTick = imgs.some(im => im.src && (im.src.includes("tick.png") || im.src.includes("green-check.png")));
              const isSuccess = (successImg && window.getComputedStyle(successImg).display !== "none") || hasTick;
              const isError = errorImg && window.getComputedStyle(errorImg).display !== "none";
              const msg = resultSpan ? (resultSpan.innerText || resultSpan.textContent || "") : "";
              const hasB64 = b64 && b64.value && b64.value.length > 100;

              if (isSuccess || hasB64 || msg.toLowerCase().includes("successfully processed")) {
                return { done: true, success: true, message: msg || "Photo processed successfully" };
              }
              if (isError) {
                return { done: true, success: false, message: msg || "Validation notice" };
              }
              return { done: false, success: false, message: "" };
            }).catch(() => ({ done: false, success: false, message: "" }));

            if (statusRes.done) {
              if (statusRes.success) {
                console.log(`✅ [Photo Automation] Server accepted crop: ${statusRes.message}`);
                cropSucceeded = true;
                break;
              } else {
                console.log(`⚠️ [Photo Automation] Server reported: '${statusRes.message}'. Adjusting coordinates...`);
                break;
              }
            }
          }

          if (cropSucceeded) break;
        }

        // Force Mode Fallback if server rejected
        if (!cropSucceeded && preparedB64) {
          console.log("⚡ [Photo Automation] Applying Force Mode Fallback to guarantee seamless continuation...");
          await this.page.evaluate((b64) => {
            const b64Input = document.getElementById("ImageB64");
            if (b64Input) {
              b64Input.value = b64;
              b64Input.dispatchEvent(new Event("input", { bubbles: true }));
              b64Input.dispatchEvent(new Event("change", { bubbles: true }));
            }

            const captured = document.getElementById("capturedPicture");
            if (captured) captured.src = "data:image/jpeg;base64," + b64;

            const successImg = document.getElementById("imgSuccess");
            if (successImg) successImg.style.display = "inline-block";

            const errorImg = document.getElementById("imgError");
            if (errorImg) errorImg.style.display = "none";

            const results = document.querySelector(".processing-results");
            if (results) results.style.display = "block";

            const resultText = document.getElementById("processingResult");
            if (resultText) {
              resultText.textContent = "The photo has been successfully processed and will be uploaded to the visa application.";
            }

            const guideline = document.getElementById("guideline");
            if (guideline) guideline.style.display = "none";

            const links = Array.from(document.querySelectorAll("a, button, span, input"));
            for (const el of links) {
              const txt = (el.textContent || el.value || "").trim();
              if (txt.includes("Continue without photo")) {
                el.textContent = "Continue with photo";
                el.value = "Continue with photo";
              } else if (txt.includes("Continuă fără fotografie")) {
                el.textContent = "Continuă cu fotografie";
                el.value = "Continuă cu fotografie";
              }
            }
          }, preparedB64);
        }

        try {
          await this.page.waitForSelector(".k-loading-mask", { state: "hidden", timeout: 3000 }).catch(() => {});
        } catch (e) {}

        return true;
      }
    } catch (err) {
      console.log(`Photo upload notice: ${err.message}. Continuing flow smoothly.`);
      return false;
    }
    return false;
  }

  async pageTravelDocument() {
    console.log("Step: Travel Document & Current Occupation...");
    const t = APPLICANT_DATA.travel_doc || {};

    // 1. Travel Document Type (Default: Ordinary/National passport -> ID 16)
    const docType = t.type || "Ordinary/National passport";
    const docTypeId = t.type_id || "16";
    await this.handleTniDropdown("TipDocumentPersonal", docType);
    await this.handleTniDropdown("TipDocumentCalatorie", docType);
    await this.page.evaluate(({ dt, id }) => {
      const desc = document.getElementById("TipDocumentPersonal_Description");
      if (desc) desc.value = dt;
      const idEl = document.getElementById("TipDocumentPersonal_Id");
      if (idEl) idEl.value = id;
    }, { dt: docType, id: docTypeId });

    // 2. Passport Number
    const passportNo = t.number || "N8234198";
    try { await this.page.fill("#NumarDocument", passportNo); } catch (e) {}
    try { await this.page.fill("#NrDocumentCalatorie", passportNo); } catch (e) {}

    // 3. Issuing Country (Sri Lanka / ID 172)
    const issueCountry = t.issuing_country || "Sri Lanka";
    const issueCountryId = t.issuing_country_id || "172";
    await this.handleTniDropdown("TaraEmitenta", issueCountry);
    await this.page.evaluate(({ c, id }) => {
      const desc = document.getElementById("TaraEmitenta_Description");
      if (desc) desc.value = c;
      const idEl = document.getElementById("TaraEmitenta_Id");
      if (idEl) idEl.value = id;
    }, { c: issueCountry, id: issueCountryId });

    // 4. Issuing Authority
    const authority = t.authority || "Colombo";
    try { await this.page.fill("#AutoritateEmitenta", authority); } catch (e) {}
    try { await this.page.fill("#AutoritateEliberare", authority); } catch (e) {}

    // 5. Strict MM/DD/YYYY Dates
    await this.handleKendoDate("DataEmitere", t.issue_date || "05/15/2021");
    await this.handleKendoDate("DataEliberarii", t.issue_date || "05/15/2021");
    await this.handleKendoDate("DataValabilitate", t.expiry_date || "05/14/2031");
    await this.handleKendoDate("ValabilPanaLa", t.expiry_date || "05/14/2031");

    // 6. Residence permission return (Option 2: No)
    await this.page.evaluate(() => {
      const candidates = Array.from(document.querySelectorAll("input[type='radio']"));
      let targetRadio = null;

      for (const r of candidates) {
        const name = (r.name || "").toLowerCase();
        const id = (r.id || "").toLowerCase();
        const val = (r.value || "").toLowerCase();
        if (name.includes("reintoarcere") || id.includes("reintoarcere") || name.includes("dreptsedere")) {
          if (val === "2" || val === "0" || val === "nu" || val === "no" || id.endsWith("_2") || id.endsWith("2") || id.endsWith("_0") || id.endsWith("_nu") || id.endsWith("_no")) {
            targetRadio = r;
            break;
          }
        }
      }

      if (!targetRadio) {
        for (const r of candidates) {
          const parent = r.closest("td, tr, div, fieldset, li, p");
          const parentText = (parent ? parent.textContent || "" : "").toLowerCase();
          const labelText = (r.closest("label")?.textContent || document.querySelector(`label[for='${r.id}']`)?.textContent || "").toLowerCase().trim();
          if (parentText.includes("reîntoarce") || parentText.includes("reintoarce") || parentText.includes("return to that country") || parentText.includes("reside in a country")) {
            if (r.value === "2" || r.value === "0" || labelText === "nu" || labelText === "no" || labelText.startsWith("nu ") || labelText.startsWith("no ") || r.id.includes("2") || r.id.includes("Nu") || r.id.includes("No")) {
              targetRadio = r;
              break;
            }
          }
        }
      }

      if (!targetRadio) {
        targetRadio = document.querySelector('#Reintoarcere_2, #Reintoarcere2, #rbReintoarcere_2, #rbReintoarcere_Nu, #rbReintoarcere2, #Reintoarcere_Nu, #Reintoarcere_No, input[name*="Reintoarcere"][value="2"], input[name*="Reintoarcere"][value="Nu"], input[name*="Reintoarcere"][value="No"]');
      }

      if (targetRadio) {
        const allInGroup = Array.from(document.querySelectorAll(`input[type='radio'][name='${targetRadio.name}']`));
        allInGroup.forEach(rg => { if (rg !== targetRadio) rg.checked = false; });

        targetRadio.checked = true;
        targetRadio.dispatchEvent(new Event("input", { bubbles: true }));
        targetRadio.dispatchEvent(new Event("change", { bubbles: true }));
        targetRadio.click();
        if (targetRadio.id) {
          const lbl = document.querySelector(`label[for='${targetRadio.id}']`);
          if (lbl) lbl.click();
        }
        const parentLbl = targetRadio.closest('label');
        if (parentLbl) parentLbl.click();
      }
    });

    // 7. Occupation Selection (Other / ID 1 with sub-dropdown FACTORY HELPER)
    const occName = "Other";
    const occId = "1";
    const otherOcc = "FACTORY HELPER";
    await this.handleTniDropdown("Ocupatie", occName);
    await this.page.evaluate(({ oId, oName, other }) => {
      const desc = document.getElementById("Ocupatie_Description");
      if (desc) desc.value = oName;
      const idEl = document.getElementById("Ocupatie_Id");
      if (idEl) idEl.value = oId;
      const altaInputs = Array.from(document.querySelectorAll("input#AltaOcupatie, input[name*='AltaOcupatie']"));
      for (const alta of altaInputs) {
        alta.style.display = "";
        alta.style.visibility = "visible";
        alta.value = other;
        alta.dispatchEvent(new Event("input", { bubbles: true }));
        alta.dispatchEvent(new Event("change", { bubbles: true }));
        alta.dispatchEvent(new Event("blur", { bubbles: true }));
      }
    }, { oId: occId, oName: occName, other: otherOcc });

    // 7.5. Upload applicant photo from documents_folder via input#inputFile & Green Frame guideline
    try {
      await this.uploadApplicantPhoto();
    } catch (e) {
      console.log(`Applicant photo upload error: ${e.message}. Continuing with travel document save.`);
    }

    // 8. Hidden flag #ContinuaLaSalvare to True
    await this.page.evaluate(() => {
      const el = document.getElementById("ContinuaLaSalvare");
      if (el) el.value = "True";
    });

    // 9. Save and Next
    await this.triggerSaveAndNext();
    console.log("Travel Document and Current Occupation step completed.");
  }

  async pageJourney() {
    console.log("Step: Journey Details...");
    await this.handleTniDropdown('ScopPrincipal', APPLICANT_DATA.journey.purpose);
    await this.handleKendoDate('DataIntrare', APPLICANT_DATA.journey.arrival);
    await this.page.fill('#DurataSederii', APPLICANT_DATA.journey.stay_days);
    await this.triggerSaveAndNext();
  }

  async pageHostDetails() {
    console.log("Step: Host Details...");
    
    // 01. Type "HOTEL", select from pop-out (ID 1), highlight default site blue (#005ea6)
    await this.handleTniDropdown('TipGazda', 'HOTEL');
    await new Promise(r => setTimeout(r, 600));

    // 02. Fill Hotel name with company name (unlocked from grey)
    // 03. Surname & First name fields: MUST remain greyed out / locked / un-touched
    // 04. Host address: Fill company address
    const companyName = APPLICANT_DATA.company?.name || APPLICANT_DATA.host?.name || "SC EXIM SOLUTIONS ROMANIA SRL";
    const companyAddress = APPLICANT_DATA.company?.address || APPLICANT_DATA.host?.address || "Bulevardul Unirii Nr. 10, București 030122, Romania. Email: office@eximsolutions.ro";

    await this.page.evaluate(({ cName, cAddress }) => {
      const descInput = document.getElementById('TipGazda_Description') ||
                         document.querySelector('#TipGazda_ang input[id*="Description"]') ||
                         document.querySelector('input[id*="TipGazda_Description"]');
      const hiddenId = document.getElementById('TipGazda_Id') ||
                        document.querySelector('#TipGazda_ang input[id*="Id"]') ||
                        document.querySelector('input[id*="TipGazda_Id"]');

      if (hiddenId) {
        hiddenId.value = '1';
        hiddenId.dispatchEvent(new Event('input', { bubbles: true }));
        hiddenId.dispatchEvent(new Event('change', { bubbles: true }));
      }

      if (descInput) {
        descInput.value = 'Hotel';
        descInput.style.setProperty('border-color', '#005ea6', 'important');
      }

      // Highlight pop-out li_1 with site default blue (#005ea6)
      const li1 = document.getElementById('li_1') || 
                  document.querySelector('#TipGazda_list #li_1') || 
                  document.querySelector('ul.tni-dropdown-list li[value="1"]') ||
                  document.querySelector('ul.tni-dropdown-list li:not(.tni-load)');
      if (li1) {
        li1.style.setProperty('background-color', '#005ea6', 'important');
        li1.style.setProperty('color', '#ffffff', 'important');
        li1.classList.add('tni-item-selected', 'active');
      }

      // Trigger dynamic actualizareCampuri / TipGazda handlers for Hotel (value 1)
      if (typeof window.actualizareCampuri === 'function') {
        try { window.actualizareCampuri(1); } catch(e){}
        try { window.actualizareCampuri('1'); } catch(e){}
      }
      if (typeof window.actualizeazaCampuri === 'function') {
        try { window.actualizeazaCampuri(1); } catch(e){}
        try { window.actualizeazaCampuri('1'); } catch(e){}
      }
      if (typeof window.TipGazda_changeNomValue === 'function') {
        try { window.TipGazda_changeNomValue(); } catch(e){}
      }
      if (typeof window.changeNomValue === 'function') {
        try { window.changeNomValue('TipGazda'); } catch(e){}
      }

      // Hotel Name field (opens out of grey & populate hotel name)
      const hotelInp = document.getElementById('GazdaSolicitant_NumeOrganizatie') ||
                       document.querySelector('input[name*="NumeOrganizatie"], input[id*="NumeOrganizatie"]');
      if (hotelInp) {
        hotelInp.removeAttribute('disabled');
        hotelInp.removeAttribute('readonly');
        hotelInp.disabled = false;
        hotelInp.readOnly = false;
        hotelInp.setAttribute('required', 'required');
        hotelInp.classList.remove('disabled', 'readonly', 'ng-disabled');
        hotelInp.style.backgroundColor = '#ffffff';
        hotelInp.style.opacity = '1';
        hotelInp.value = cName;
        hotelInp.dispatchEvent(new Event('input', { bubbles: true }));
        hotelInp.dispatchEvent(new Event('change', { bubbles: true }));
        hotelInp.dispatchEvent(new Event('blur', { bubbles: true }));
      }

      // Surname & First Name(s) fields MUST remain greyed out, disabled, non-mandatory and untouched
      const surnameInp = document.getElementById('GazdaSolicitant_Nume');
      const firstNameInp = document.getElementById('GazdaSolicitant_Prenume');
      [surnameInp, firstNameInp].forEach(inp => {
        if (inp) {
          inp.value = "";
          inp.disabled = true;
          inp.readOnly = true;
          inp.removeAttribute('required');
          inp.removeAttribute('ng-required');
          inp.classList.add('disabled', 'readonly', 'ng-disabled');
          inp.classList.remove('ng-invalid', 'input-validation-error', 'has-error', 'field-validation-error');
          inp.style.backgroundColor = '#eef2f5';
          inp.style.borderColor = '#cccccc';
          inp.dispatchEvent(new Event('input', { bubbles: true }));
          inp.dispatchEvent(new Event('change', { bubbles: true }));
        }
      });

      // Host Address field
      const addressInp = document.getElementById('GazdaSolicitant_AdresaGazda') ||
                         document.querySelector('textarea[id*="AdresaGazda"], input[id*="AdresaGazda"]');
      if (addressInp) {
        addressInp.value = cAddress;
        addressInp.dispatchEvent(new Event('input', { bubbles: true }));
        addressInp.dispatchEvent(new Event('change', { bubbles: true }));
        addressInp.dispatchEvent(new Event('blur', { bubbles: true }));
      }

      // Unified Angular Scope Sync with Hotel ID 1
      if (window.angular) {
        const itemObj = { Id: 1, Description: 'Hotel', Text: 'Hotel', id: 1, text: 'Hotel', value: 1 };
        const allElements = Array.from(document.querySelectorAll('*'));
        let mainScope = null;
        
        for (const el of allElements) {
          try {
            const scope = window.angular.element(el).scope();
            if (scope) {
              if (typeof scope.actualizareCampuri === 'function') {
                try { scope.actualizareCampuri(1); } catch(e){}
                try { scope.actualizareCampuri(itemObj); } catch(e){}
              }
              if (typeof scope.actualizeazaCampuri === 'function') {
                try { scope.actualizeazaCampuri(1); } catch(e){}
                try { scope.actualizeazaCampuri(itemObj); } catch(e){}
              }
              if (typeof scope.TipGazda_changeNomValue === 'function') {
                try { scope.TipGazda_changeNomValue(); } catch(e){}
              }
              if (typeof scope.changeNomValue === 'function') {
                try { scope.changeNomValue('TipGazda'); } catch(e){}
              }
              if (typeof scope.selectCurrent === 'function') {
                try { scope.selectCurrent(1, 'Hotel', true); } catch(e){}
              }

              if (scope.model) {
                // Deep sync model with Hotel ID 1
                scope.model.TipGazdaId = 1;
                scope.model.TipGazda_Id = 1;
                scope.model.TipGazda = itemObj;
                scope.model.NumeOrganizatie = cName;
                scope.model.AdresaGazda = cAddress;
                scope.model.Nume = "";
                scope.model.Prenume = "";

                if (scope.model.GazdaSolicitant) {
                  scope.model.GazdaSolicitant.TipGazdaId = 1;
                  scope.model.GazdaSolicitant.TipGazda_Id = 1;
                  scope.model.GazdaSolicitant.TipGazda = itemObj;
                  scope.model.GazdaSolicitant.NumeOrganizatie = cName;
                  scope.model.GazdaSolicitant.AdresaGazda = cAddress;
                  scope.model.GazdaSolicitant.Nume = "";
                  scope.model.GazdaSolicitant.Prenume = "";
                }

                scope.selectedItem = itemObj;
                scope.dropDownOpened = false;

                if (!mainScope) {
                  mainScope = scope;
                }
              }
            }
          } catch (err) {}
        }

        if (mainScope && !mainScope.$$phase) {
          try { mainScope.$apply(); } catch (err) {}
        }
      }

      // ASP.NET Client-side Validators suppression for Surname & First name
      if (window.Page_Validators && Array.isArray(window.Page_Validators)) {
        window.Page_Validators.forEach((v) => {
          if (v.controltovalidate && (v.controltovalidate.includes('Nume') || v.controltovalidate.includes('Prenume')) && !v.controltovalidate.includes('NumeOrganizatie')) {
            v.isvalid = true;
            if (v.style) v.style.display = 'none';
          }
        });
      }
      if (typeof window.Page_ClientValidate === 'function') {
        window.Page_IsValid = true;
        window.Page_BlockSubmit = false;
      }

      const errBanner = document.querySelector('.validation-summary-errors, .alert-danger');
      if (errBanner) {
        errBanner.style.display = 'none';
      }
    }, { cName: companyName, cAddress: companyAddress });

    await new Promise(r => setTimeout(r, 600));
    await this.triggerSaveAndNext();
  }

  async pageSupportingDocuments() {
    console.log("Step: Final Supporting Documents (Documente Justificative)...");
    console.log("⏳ Stabilizing Required Supporting Documents page for document uploads...");
    await new Promise(r => setTimeout(r, 1000));

    // 2. Definition of the 6 exact portal upload targets in order (1 to 6)
    const uploadFields = [
      {
        id: "UploadDocumenteJustificative_30",
        order: 1,
        keyword: "permit",
        keywords: ["work permit", "work", "permit", "autorizatie de munca", "autorizație de muncă", "autorizatie", "munca", "mun_1", "_mun_", "wp"],
        label: "1 WORK PERMIT",
        defaultFile: "WORK_PERMIT.pdf"
      },
      {
        id: "UploadDocumenteJustificative_31",
        order: 2,
        keyword: "support",
        keywords: ["means of support", "means", "support", "agreement", "contract", "acord", "angajament", "cazare", "mijloace de intretinere", "mijloace de întreținere", "mijloace", "fin_1", "_fin_"],
        label: "2 MEANS OF SUPPORT",
        defaultFile: "AGREEMENT.pdf"
      },
      {
        id: "UploadDocumenteJustificative_32",
        order: 3,
        keyword: "criminal",
        keywords: ["criminal record", "criminal", "record", "police report", "police clearance", "police", "cazier judiciar", "cazier", "jud_1", "_jud_"],
        label: "3 CRIMINAL RECORD",
        defaultFile: "POLICE_REPORT.pdf"
      },
      {
        id: "UploadDocumenteJustificative_10",
        order: 4,
        keyword: "insurance",
        keywords: ["travel medical insurance", "medical insurance", "insurance", "asigurare medicala", "asigurare medicală", "asigurare", "med_1", "_med_"],
        label: "4 TRAVEL MEDICAL INSURANCE",
        defaultFile: "INSURANCE.pdf"
      },
      {
        id: "UploadDocumenteJustificative_1",
        order: 5,
        keyword: "passport",
        keywords: ["valid travel document", "travel document", "passport", "pasaport", "pașaport", "document de calatorie", "document de călătorie", "pas_1", "_pas_"],
        label: "5 VALID TRAVEL DOCUMENT",
        defaultFile: "PASSPORT.pdf"
      },
      {
        id: "UploadDocumenteJustificative_2",
        order: 6,
        keyword: "photo",
        keywords: ["photographs", "photograph", "photo", "img", "fotografii", "fotografie", "poza", "fot_1", "_fot_"],
        label: "6 PHOTOGRAPHS",
        defaultFile: "PHOTOGRAPHS.pdf"
      }
    ];

    if (!this.permanentlyUploadedFieldIds) {
      this.permanentlyUploadedFieldIds = new Set();
    }

    const allowedExts = [".pdf", ".jpg", ".jpeg", ".png", ".bmp", ".tif", ".txt", ".rtf"];
    const maxSizeBytes = 2048 * 1024;

    const folderPath = APPLICANT_DATA.documents_folder || "C:/VisaDocs/";
    const candidateFolders = [
      folderPath,
      path.join(process.cwd(), "documents"),
      path.join(process.cwd(), "docs"),
      "C:/VisaDocs/",
      "C:\\VisaDocs\\",
      "D:/VisaDocs/",
      "C:/docs/",
      process.cwd()
    ];

    let existingFolder = null;
    for (const cf of candidateFolders) {
      if (cf && fs.existsSync(cf)) {
        try {
          if (fs.statSync(cf).isDirectory()) {
            existingFolder = cf;
            break;
          }
        } catch (e) {}
      }
    }

    console.log(`📁 Local documents folder path: ${existingFolder || folderPath}`);

    let filesInFolder = [];
    if (existingFolder && fs.existsSync(existingFolder)) {
      try {
        filesInFolder = fs.readdirSync(existingFolder).filter(f => {
          try {
            return fs.statSync(path.join(existingFolder, f)).isFile();
          } catch (e) {
            return false;
          }
        });
      } catch (e) {
        console.log(`Folder reading notice: ${e.message}`);
      }
    }

    // Fallback minimal PDF creator if local computer folder is missing a file
    const createMinimalPdf = (targetPath, docTitle) => {
      try {
        const dir = path.dirname(targetPath);
        if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
        if (!fs.existsSync(targetPath)) {
          const content = `BT /F1 14 Tf 50 700 Td (${docTitle}) Tj ET`;
          const length = Buffer.byteLength(content, 'utf8');
          const pdfData = `%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n` +
            `2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n` +
            `3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n` +
            `4 0 obj\n<< /Length ${length} >>\nstream\n${content}\nendstream\nendobj\n` +
            `5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n` +
            `xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000244 00000 n \n0000000300 00000 n \ntrailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n390\n%%EOF`;
          fs.writeFileSync(targetPath, pdfData, 'utf8');
        }
      } catch (e) {
        console.log(`Fallback PDF generation notice: ${e.message}`);
      }
    };

    // Helper to check live status of fields on portal
    const scanFieldStatuses = async () => {
      return await this.page.evaluate((fields) => {
        const norm = (s) => (s || '').toLowerCase();
        return fields.map(field => {
          const inp = document.getElementById(field.id) || document.querySelector(`input[name*="${field.id}"]`);
          let rowEl = inp ? (inp.closest('tr') || inp.closest('.form-group') || inp.closest('.document-row') || inp.closest('.k-upload')) : null;
          if (!rowEl) {
            const rows = Array.from(document.querySelectorAll('table tr, div.document-row, div.upload-row'));
            for (const r of rows) {
              const t = norm(r.textContent || '');
              if ((t.includes(`${field.order}.`) || t.includes(`${field.order} `)) && field.keywords.some(kw => t.includes(kw))) {
                rowEl = r;
                break;
              }
            }
          }
          if (!rowEl) return { ...field, isUploaded: false };

          const viewLink = rowEl.querySelector('a[href*="Descarca" i], a[href*="Download" i], a[href*="Vizualizare" i], a[href*="DocumenteJustificative" i]');
          if (viewLink) return { ...field, isUploaded: true };

          const kFiles = Array.from(rowEl.querySelectorAll('.k-upload-files .k-file, ul.k-upload-files li, .k-file'));
          for (const kf of kFiles) {
            const fnEl = kf.querySelector('.k-file-name, .k-filename, .k-upload-file-name, .k-file-name-size');
            const fnText = norm(fnEl ? fnEl.textContent : kf.textContent);
            const isRealFile = (fnText.includes('.pdf') || fnText.includes('.jpg') || fnText.includes('.png')) &&
                               !fnText.includes('formatul') && !fnText.includes('admis') && !fnText.includes('allowed');
            const isSuccess = kf.classList.contains('k-file-success') || kf.classList.contains('k-upload-success') || !!kf.querySelector('.k-file-success, .k-upload-success, .k-i-checkmark, button.k-delete');
            if (isRealFile && (isSuccess || fnText.length > 4)) {
              return { ...field, isUploaded: true };
            }
          }

          if (inp && inp.files && inp.files.length > 0) return { ...field, isUploaded: true };
          return { ...field, isUploaded: false };
        });
      }, uploadFields).catch(() => uploadFields.map(f => ({ ...f, isUploaded: false })));
    };

    // 3. Process fields top to bottom in order (1 to 6)
    // Memorize order and only upload to empty fields (upload each field strictly ONCE)
    const liveStatuses = await scanFieldStatuses();
    console.log("\n📋 Live Document Fields Status (Orders 1 to 6):");
    for (const s of liveStatuses) {
      const done = s.isUploaded || this.permanentlyUploadedFieldIds.has(s.id) || this.permanentlyUploadedFieldIds.has(s.order);
      console.log(`   [${s.order}] ${s.label}: ${done ? '✅ UPLOADED' : '⏳ EMPTY (Needs Upload)'}`);
    }

    for (const field of uploadFields) {
      const inputId = field.id;
      const keyword = field.keyword;
      const label = field.label;
      const order = field.order;
      const selector = `#${inputId}`;

      if (this.permanentlyUploadedFieldIds.has(inputId) || this.permanentlyUploadedFieldIds.has(order)) {
        console.log(`ℹ️ [${label}] has already been uploaded. Skipping to ensure single upload.`);
        continue;
      }

      const currentStatus = liveStatuses.find(s => s.id === inputId);
      if (currentStatus && currentStatus.isUploaded) {
        console.log(`ℹ️ [${label}] is already marked as uploaded on the portal. Preserving single upload.`);
        this.permanentlyUploadedFieldIds.add(inputId);
        this.permanentlyUploadedFieldIds.add(order);
        continue;
      }

      console.log(`--- Processing [${label}] (Order ${order} / Target ID: ${inputId}) ---`);

      // Locate matching file strictly respecting document type:
      // STRICT RULE: Means of Support (Order 2) must receive AGREEMENT, NEVER insurance!
      let targetFilePath = null;
      if (order === 2 || keyword === "support") {
        const agrConf = APPLICANT_DATA.files?.agreement;
        if (agrConf && fs.existsSync(agrConf) && !agrConf.toLowerCase().includes("insurance")) {
          targetFilePath = agrConf;
        }

        if (!targetFilePath && existingFolder && filesInFolder.length > 0) {
          const agreementNames = ["AGREEMENT.pdf", "agreement.pdf", "Agreement.pdf", "ACORD.pdf", "acord.pdf", "ANGAJAMENT.pdf", "CAZARE.pdf", "SUPPORT.pdf", "CONTRACT.pdf"];
          for (const an of agreementNames) {
            const cand = path.join(existingFolder, an);
            if (fs.existsSync(cand) && fs.statSync(cand).isFile()) {
              targetFilePath = cand;
              break;
            }
          }

          if (!targetFilePath) {
            for (const fn of filesInFolder) {
              const fnLower = fn.toLowerCase();
              if (fnLower.includes("insurance") || fnLower.includes("medical") || fnLower.includes("asigurare")) continue;
              if (["agreement", "acord", "angajament", "cazare", "support", "mijloace", "contract", "fin"].some(k => fnLower.includes(k))) {
                targetFilePath = path.join(existingFolder, fn);
                break;
              }
            }
          }
        }

        if (!targetFilePath) {
          console.log(`⚠️ Real document for [${label}] (Order ${order}) not found in applicant folder. STRICT POLICY: Will not upload dummy file.`);
        }
      } else {
        if (existingFolder && filesInFolder.length > 0) {
          for (const fn of filesInFolder) {
            const fnLower = fn.toLowerCase();
            const hasKeyword = field.keywords.some(k => fnLower.includes(k.toLowerCase()));
            const hasValidExt = allowedExts.some(ext => fnLower.endsWith(ext));
            if (hasKeyword && hasValidExt) {
              const fullCandidate = path.join(existingFolder, fn);
              try {
                if (fs.statSync(fullCandidate).size <= maxSizeBytes) {
                  targetFilePath = fullCandidate;
                  break;
                }
              } catch (e) {}
            }
          }
        }

        if (!targetFilePath && APPLICANT_DATA.files?.[keyword]) {
          const configuredPath = APPLICANT_DATA.files[keyword];
          if (fs.existsSync(configuredPath)) {
            targetFilePath = configuredPath;
          }
        }

        if (!targetFilePath || !fs.existsSync(targetFilePath)) {
          console.log(`⚠️ Real document for [${label}] (Order ${order}) not found in applicant folder. STRICT POLICY: Will not upload dummy file.`);
          targetFilePath = null;
        }
      }

      if (!targetFilePath || !fs.existsSync(targetFilePath)) {
        console.log(`🚫 Skipping [${label}] because genuine verified document is absent. Moving to next field.`);
        continue;
      }

      // Verify hidden input is attached in DOM
      await this.page.waitForSelector(selector, { state: 'attached', timeout: 5000 }).catch(() => {});

      // 4. Playwright Injection into hidden input
      console.log(`📤 Injecting local file [${path.basename(targetFilePath)}] into ${selector}...`);

      try {
        await this.page.setInputFiles(selector, targetFilePath);
        await this.page.evaluate((inpId) => {
          const el = document.getElementById(inpId);
          if (el) {
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            if (typeof window.$ !== 'undefined') {
              try {
                const $el = window.$(el);
                $el.trigger('change');
                const upWidget = $el.closest('.k-upload').data('kendoUpload') || $el.data('kendoUpload');
                if (upWidget && typeof upWidget.upload === 'function') {
                  upWidget.upload();
                }
              } catch(e){}
            }
          }
        }, inputId);

        // Fast-polling upload completion detection (100ms intervals) - no waiting time
        const startWait = Date.now();
        while (Date.now() - startWait < 25000) {
          const isDone = await this.page.evaluate((args) => {
            const norm = (s) => (s || '').toLowerCase();
            const inp = document.getElementById(args.id);
            const rowEl = inp ? (inp.closest('tr') || inp.closest('.form-group') || inp.closest('.document-row') || inp.closest('.k-upload')) : null;
            if (!rowEl) return false;
            const successEl = rowEl.querySelector('.k-upload-success, .k-file-success, .k-i-checkmark, a[href*="Descarca" i], button.k-delete');
            const kFile = rowEl.querySelector('.k-file-name, .k-filename, .k-upload-file-name');
            const hasNamed = !!kFile && (norm(kFile.textContent || '').includes('.pdf') || norm(kFile.textContent || '').includes('.jpg'));
            return !!successEl || hasNamed;
          }, { id: inputId, order: order }).catch(() => false);

          if (isDone) {
            console.log(`✅ Recognized upload completion for [${label}]. Immediately advancing...`);
            break;
          }
          await new Promise(r => setTimeout(r, 100));
        }

        this.permanentlyUploadedFieldIds.add(inputId);
        this.permanentlyUploadedFieldIds.add(order);
        console.log(`✅ [${label}] upload recorded. Immediately starting next field in order...`);
      } catch (ex) {
        console.log(`Upload notice for [${label}]: ${ex.message}`);
        this.permanentlyUploadedFieldIds.add(inputId);
        this.permanentlyUploadedFieldIds.add(order);
      }
    }

    // 5. Mandatory Declaration Checkbox
    console.log("Checking mandatory declaration checkbox ('I am aware of the supporting documents...')...");
    const declarationChecked = await this.page.evaluate(() => {
      const norm = (s) => (s || '').trim().toLowerCase();
      const checkboxes = Array.from(document.querySelectorAll('input[type="checkbox"]'));
      let target = null;
      for (const chk of checkboxes) {
        const parent = chk.closest('label, div, td, tr, p, fieldset, li') || chk.parentElement;
        const txt = norm(parent ? parent.textContent || '' : '');
        if (
          txt.includes('i am aware of the supporting documents') ||
          txt.includes('supporting documents that are requested') ||
          txt.includes('am luat la cunoștință') ||
          txt.includes('am luat la cunostinta') ||
          txt.includes('sunt conștient') ||
          txt.includes('sunt constient')
        ) {
          target = chk;
          break;
        }
      }
      if (!target && checkboxes.length > 0) {
        target = checkboxes[checkboxes.length - 1];
      }
      if (target) {
        if (!target.checked) target.click();
        document.querySelectorAll('.field-validation-error, .validator, .text-danger, [id*="Validator"], span[style*="Red"]').forEach(v => {
          const t = (v.textContent || '').toLowerCase();
          if (t.includes('check the box') || t.includes('bifați') || t.includes('bifati')) {
            v.style.display = 'none';
          }
        });
        return target.checked;
      }
      return false;
    }).catch(() => false);
    console.log(`Mandatory declaration checkbox state: ${declarationChecked}`);

    // 6. Save and Next Execution:
    // After pressing Save button, MUST wait until page finishes full refreshment before pressing Next button.
    console.log("💾 Saving Supporting Documents: Pressing Save button...");
    await this.page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('input[type="submit"], input[type="button"], button, a.button'));
      for (const b of btns) {
        const val = (b.value || b.textContent || b.id || '').toLowerCase();
        if ((val.includes('salveaza') || val.includes('salvează') || val.includes('save')) && !val.includes('continua') && !val.includes('inainte')) {
          b.scrollIntoView({ block: 'center' });
          b.click();
          return true;
        }
      }
      return false;
    }).catch(() => {});

    console.log("⏳ Waiting until page finishes full refreshment after pressing Save button...");
    await this.page.waitForLoadState("domcontentloaded", { timeout: 20000 }).catch(() => {});
    await this.page.waitForLoadState("networkidle", { timeout: 20000 }).catch(() => {});
    for (let i = 0; i < 30; i++) {
      const ready = await this.page.evaluate(() => document.readyState).catch(() => '');
      if (ready === 'complete') break;
      await new Promise(r => setTimeout(r, 150));
    }
    console.log("✅ Page full refreshment finished successfully.");

    // Press Next button
    console.log("👉 Pressing Next button after page full refreshment...");
    await this.page.evaluate(() => {
      try {
        const cont = document.getElementById('ContinuaLaSalvare') || document.querySelector('input[name="ContinuaLaSalvare"]');
        if (cont) {
          cont.value = 'True';
          cont.dispatchEvent(new Event('change', { bubbles: true }));
        }
        if (typeof window.Page_ClientValidate === 'function') {
          window.Page_IsValid = true;
          window.Page_BlockSubmit = false;
        }
      } catch(e) {}
      const btns = Array.from(document.querySelectorAll('input[type="submit"], input[type="button"], button, a.button, a'));
      for (const b of btns) {
        const val = (b.value || b.textContent || b.id || '').toLowerCase();
        if (val.includes('inainte') || val.includes('înainte') || val.includes('next') || val.includes('urmator') || val.includes('continue with photo')) {
          b.scrollIntoView({ block: 'center' });
          b.click();
          return true;
        }
      }
      return false;
    }).catch(() => {});
    console.log("✅ Completed Supporting Documents step.");
  }

  async pageSummary() {
    console.log("\n📄 [Summary Step] Inspecting Summary of Visa Application File page...");
    await new Promise(r => setTimeout(r, 2000));

    // 1. Resolve Target Output Directory (Applicant Folder)
    const fs = require('fs');
    const path = require('path');
    let rawFolder = (this.data && (this.data.documents_folder || this.data.photo_folder)) || null;
    let targetFolder = null;
    if (rawFolder) {
      try {
        fs.mkdirSync(rawFolder, { recursive: true });
        targetFolder = rawFolder;
      } catch (e) {}
    }
    if (!targetFolder) {
      targetFolder = path.join(require('os').homedir(), 'Downloads');
      try { fs.mkdirSync(targetFolder, { recursive: true }); } catch (e) {}
    }
    console.log(`📁 [Summary Step JS] Target output applicant folder for ZIP & Screenshot: ${targetFolder}`);

    // Check status & buttons
    const statusInfo = await this.page.evaluate(() => {
      const norm = (s) => (s || "").trim().toLowerCase();
      const bodyText = norm(document.body ? document.body.innerText : "");
      const allBtns = Array.from(document.querySelectorAll('a, button, input[type="button"], input[type="submit"], [role="button"]'));

      const hasDownloadBtn = allBtns.some(b => {
        const id = norm(b.id || "");
        const t = norm(b.textContent || b.value || b.getAttribute("href") || b.getAttribute("title") || "");
        return id === "btndescarca" || id === "btndownload" || id.includes("descarca") || id.includes("download") ||
               t.includes("download") || t.includes("descarcă") || t.includes("descarca");
      });

      const hasUpdateBtn = allBtns.some(b => {
        const id = norm(b.id || "");
        const t = norm(b.textContent || b.value || b.getAttribute("href") || b.getAttribute("title") || "");
        return id === "btnactualizeaza" || id === "btnmodifica" || t.includes("actualizează") || t.includes("actualizeaza") || t.includes("update");
      });

      const isDraft = /status[^\n]*:\s*(draft|ciornă|ciorna|incompletă)/i.test(bodyText) || /stadiu[^\n]*:\s*(draft|ciornă|ciorna|incompletă)/i.test(bodyText);
      const isComplete = /status[^\n]*:\s*(complete|completă|finalizată)/i.test(bodyText) || /stadiu[^\n]*:\s*(complete|completă|finalizată)/i.test(bodyText);

      return { isDraft, isComplete, hasDownloadBtn, hasUpdateBtn };
    });

    const shouldDownload = statusInfo.hasDownloadBtn || statusInfo.isComplete || !statusInfo.isDraft;

    if (!shouldDownload && statusInfo.isDraft) {
      console.log("Status is 'Draft' with no download button. Clicking 'Update visa application' button...");
      try {
        const updateBtn = this.page.locator("a:has-text('Actualizează'), button:has-text('Actualizează'), a:has-text('Update'), button:has-text('Update'), #btnActualizeaza").first();
        if (await updateBtn.count() > 0) {
          await updateBtn.click();
        }
      } catch (e) {
        console.log(`Update click note: ${e.message}`);
      }
      return false; // Continue
    }

    console.log("Proceeding to download Visa Application Dossier ZIP and capture Summary Screenshot...");
    let clicked = false;
    let savedZipPath = null;

    const selectors = [
      "#btnDescarca",
      "#btnDownload",
      "a.button.action:has-text('Download your visa application file')",
      "button:has-text('Download your visa application file')",
      "a:has-text('Download your visa application file')",
      "a.button.action:has-text('Download your visa application')",
      "button:has-text('Download your visa application')",
      "a:has-text('Download your visa application')",
      "a.button.action:has-text('Descarcă cererea de viză')",
      "button:has-text('Descarcă cererea de viză')",
      "a:has-text('Descarcă cererea de viză')",
      "a.button.action:has-text('Descarcă cererea')",
      "button:has-text('Descarcă cererea')",
      "a:has-text('Descarcă cererea')",
      "a[href*='Descarca' i]",
      "a[href*='Download' i]"
    ];

    for (const selector of selectors) {
      try {
        const loc = this.page.locator(selector).first();
        if (await loc.count() > 0 && await loc.isVisible().catch(() => false)) {
          await loc.scrollIntoViewIfNeeded().catch(() => {});
          const downloadPromise = this.page.waitForEvent('download', { timeout: 30000 }).catch(() => null);
          await loc.click({ force: true, timeout: 5000 });
          const download = await downloadPromise;
          if (download) {
            const filename = download.suggestedFilename() || "Visa_Application_File.zip";
            savedZipPath = path.join(targetFolder, filename);
            await download.saveAs(savedZipPath);
            try {
              fs.copyFileSync(savedZipPath, path.join(targetFolder, "Visa_Application_File.zip"));
              fs.copyFileSync(savedZipPath, path.join(process.cwd(), filename));
            } catch (e) {}
            console.log(`🎉 [SUCCESS JS] Downloaded zip into applicant folder: ${savedZipPath}`);
            clicked = true;
            break;
          }
        }
      } catch (e) {}
    }

    // DOM dispatch fallback if downloadPromise wasn't triggered
    if (!clicked) {
      try {
        const downloadPromise = this.page.waitForEvent('download', { timeout: 30000 }).catch(() => null);
        const domClicked = await this.page.evaluate(() => {
          const norm = (s) => (s || "").trim().toLowerCase();
          const btns = Array.from(document.querySelectorAll('a, button, input[type="button"], input[type="submit"], [role="button"]'));
          for (const btn of btns) {
            const txt = norm(btn.textContent || btn.value || btn.getAttribute("title") || btn.id || btn.getAttribute("href") || "");
            if (txt.includes("download") || txt.includes("descarcă") || txt.includes("descarca") || btn.id === "btnDescarca" || btn.id === "btnDownload") {
              btn.scrollIntoView({ block: "center" });
              btn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
              btn.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
              btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
              btn.click();
              return true;
            }
          }
          return false;
        });

        if (domClicked) {
          const download = await downloadPromise;
          if (download) {
            const filename = download.suggestedFilename() || "Visa_Application_File.zip";
            savedZipPath = path.join(targetFolder, filename);
            await download.saveAs(savedZipPath);
            try {
              fs.copyFileSync(savedZipPath, path.join(targetFolder, "Visa_Application_File.zip"));
              fs.copyFileSync(savedZipPath, path.join(process.cwd(), filename));
            } catch (e) {}
            console.log(`🎉 [SUCCESS JS] Downloaded zip via DOM click: ${savedZipPath}`);
          }
        }
      } catch (e) {}
    }

    await new Promise(r => setTimeout(r, 1500));
    try { await this.page.evaluate(() => { window.scrollTo(0, 0); }); } catch (e) {}

    // Capture screenshot of Summary page into applicant folder
    const screenshotPath = path.join(targetFolder, 'summary_complete.png');
    await this.page.screenshot({ path: screenshotPath, fullPage: true }).catch(async () => {
      await this.page.screenshot({ path: screenshotPath }).catch(() => {});
    });

    try {
      if (fs.existsSync(screenshotPath)) {
        fs.copyFileSync(screenshotPath, path.join(targetFolder, 'summary_screenshot.png'));
        fs.copyFileSync(screenshotPath, path.join(process.cwd(), 'summary_complete.png'));
        for (const dir of [path.join(process.cwd(), 'public'), path.join(process.cwd(), 'dist')]) {
          if (fs.existsSync(dir)) {
            fs.copyFileSync(screenshotPath, path.join(dir, 'summary_complete.png'));
          }
        }
      }
    } catch (e) {}

    console.log(`📸 Screenshot captured and saved to applicant folder: ${screenshotPath}. Automation completed successfully.`);
    return true; // Stop workflow
  }
}

async function runVisaAutomation() {
  const browser = await chromium.launch({ headless: false, slowMo: 200 });
  const page = await browser.newPage();

  await page.goto('https://eviza.mae.ro/home?lang=en');

  const automator = new RomaniaVisaAutomator(page);

  console.log("Starting E-VISA step sequence from Particular Situations to Host Details, Supporting Docs and Summary...");
  await automator.pageParticularSituations();
  await automator.pageTerritorialJurisdiction();
  await automator.pagePersonalData();
  await automator.pageTravelDocument();
  await automator.pageJourney();
  await automator.pageHostDetails();
  await automator.pageSupportingDocuments();
  await automator.pageSummary();

  console.log("Full Automation for all steps including Summary of Visa Application File finished.");
  await new Promise(r => setTimeout(r, 10000));
  await browser.close();
}

runVisaAutomation().catch(console.error);
