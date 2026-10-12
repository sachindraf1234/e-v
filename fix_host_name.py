import os

filepath = 'server.ts'
with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# 1. Update Puppeteer block
target1_start = 'const hostSelectors = ['
target1_end = 'if (filled) {'

idx1 = content.find(target1_start, 8900)
idx2 = content.find(target1_end, idx1)

if idx1 != -1 and idx2 != -1:
    new_puppeteer = """const hostSelectors = [
          "#DateCalatorie_NumeGazda", "#DateCalatorie_DenumireGazda", "#NumeGazda", "#DenumireGazda",
          "input[id*=\\"NumeGazda\\" i]", "input[name*=\\"NumeGazda\\" i]",
          "input[id*=\\"HostName\\" i]", "input[name*=\\"HostName\\" i]",
          "input[id*=\\"DenumireGazda\\" i]", "input[id*=\\"Gazda\\" i]", "input[name*=\\"Gazda\\" i]",
          "#DateCalatorie_CineSuporta", "#CineSuporta", "input[id*=\\"CineSuporta\\" i]", "input[name*=\\"CineSuporta\\" i]",
          "input[id*=\\"Sponsor\\" i]", "input[name*=\\"Sponsor\\" i]"
        ];
        
        let found = false;
        const hostEls = Array.from(document.querySelectorAll<HTMLInputElement>(hostSelectors.join(", ")));
        
        // Also find by label
        const allInps = Array.from(document.querySelectorAll<HTMLInputElement>("input[type=\\"text\\"], input:not([type])"));
        for (const inp of allInps) {
          const lbl = (inp.closest('tr, td, label, div.form-group')?.textContent || '').toLowerCase();
          if (lbl.includes('host person') || lbl.includes('host company') || lbl.includes('gazda') || lbl.includes('sponsor') || lbl.includes('cine suporta')) {
            if (!lbl.includes('aviz') && !lbl.includes('permit') && !lbl.includes('autoriza')) {
              if (!hostEls.includes(inp)) hostEls.push(inp);
            }
          }
        }
        
        for (const hostEl of hostEls) {
          hostEl.focus();
          hostEl.value = cName;
          hostEl.setAttribute("value", cName);
          hostEl.dispatchEvent(new Event("input", { bubbles: true }));
          hostEl.dispatchEvent(new Event("change", { bubbles: true }));
          hostEl.dispatchEvent(new Event("blur", { bubbles: true }));
          try {
            if ((window as any).angular) {
              const ngEl = (window as any).angular.element(hostEl);
              const scope = ngEl.scope();
              if (scope) {
                if (scope.model) {
                  scope.model.NumeGazda = cName;
                  scope.model.DenumireGazda = cName;
                  scope.model.CineSuporta = cName;
                  if (scope.model.DateCalatorie) {
                    scope.model.DateCalatorie.NumeGazda = cName;
                    scope.model.DateCalatorie.DenumireGazda = cName;
                    scope.model.DateCalatorie.CineSuporta = cName;
                  }
                }
                const modelCtrl = ngEl.controller("ngModel");
                if (modelCtrl) {
                  modelCtrl.$setViewValue(cName);
                  modelCtrl.$commitViewValue();
                  modelCtrl.$setValidity("required", true);
                  modelCtrl.$render();
                }
                if (scope.$apply && !scope.$$phase) scope.$apply();
              }
            }
          } catch(e) {}
          found = true;
        }
        return found;
      }, companyName);
      """
    
    content = content[:idx1] + new_puppeteer + content[idx2:]
    print("Puppeteer block replaced!")
else:
    print("Puppeteer block not found")

# 2. Update Python Playwright block
target2_start = 'const compSelectors = "#DateCalatorie_NumePJ'
target2_end = 'fillWithAngular(document.querySelector("#DateCalatorie_TelefonPJ'

idx3 = content.find(target2_start, 11500)
idx4 = content.find(target2_end, idx3)

if idx3 != -1 and idx4 != -1:
    new_python = """const compSelectors = "#DateCalatorie_NumePJ, #NumePJ, #NumeCompanie, #DateCalatorie_DenumirePJ, #DenumirePJ, #CompanyContact_Nume, input[name*='NumePJ'], input[name*='DenumirePJ'], input[name*='NumeCompanie']";
                    const hostSelectors = "#DateCalatorie_NumeGazda, #NumeGazda, #DenumireGazda, #HostName, #DateCalatorie_CineSuporta, #CineSuporta, input[name*='NumeGazda'], input[name*='DenumireGazda'], input[name*='HostName'], input[id*='Gazda'], input[name*='CineSuporta'], input[id*='Sponsor']";
                    
                    const compEls = Array.from(document.querySelectorAll(compSelectors));
                    for (const el of compEls) {
                        fillWithAngular(el, cName, ["NumeCompanie", "CompanyContact_Nume", "NumePersoanaContact", "ContactPerson", "DenumireCompanie", "NumePJ", "DateCalatorie_NumePJ"]);
                    }
                    const hostEls = Array.from(document.querySelectorAll(hostSelectors));
                    for (const el of hostEls) {
                        el.value = "";
                        fillWithAngular(el, cName, ["NumeGazda", "DenumireGazda", "DateCalatorie_NumeGazda", "DateCalatorie_DenumireGazda", "CineSuporta", "DateCalatorie_CineSuporta"]);
                    }
                    
                    const allInps = Array.from(document.querySelectorAll('input[type="text"], input:not([type])'));
                    for (const inp of allInps) {
                        const lbl = (inp.closest('tr, td, label, div.form-group')?.textContent || '').toLowerCase();
                        if (lbl.includes('host person') || lbl.includes('host company') || lbl.includes('gazda') || lbl.includes('sponsor') || lbl.includes('cine suporta')) {
                            if (!lbl.includes('aviz') && !lbl.includes('permit') && !lbl.includes('autoriza')) {
                                fillWithAngular(inp, cName, ["NumeGazda", "DenumireGazda", "CineSuporta", "DateCalatorie_CineSuporta"]);
                            }
                        }
                        if (inp.value && (inp.value === wpNum || inp.value.includes(wpNum))) {
                            if (!lbl.includes('aviz') && !lbl.includes('permit') && !lbl.includes('autoriza')) {
                                fillWithAngular(inp, cName, ["NumeGazda", "DenumireGazda", "CineSuporta", "DateCalatorie_CineSuporta"]);
                            }
                        }
                    }
                    
                    """
    content = content[:idx3] + new_python + content[idx4:]
    print("Python Playwright block replaced!")
else:
    print("Python Playwright block not found")

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
