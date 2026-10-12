/**
 * Calculates arrival, departure, and insurance dates according to Romanian Visa requirements:
 * - Arrival: Today's date of next month (same day of the month, next month)
 * - Departure: Exactly 3 months from today's date of next month (arrival date)
 * - Insurance Valid Until: Standard coverage period (default 6 months from arrival)
 *
 * Handles edge cases like months with fewer days (e.g. Jan 31 -> Feb 28/29) cleanly.
 */
export function calculateJourneyAndInsuranceDates(baseDate: Date = new Date()) {
  const now = baseDate;

  // Arrival: Today's day in next month
  const arrYear = now.getFullYear() + Math.floor((now.getMonth() + 1) / 12);
  const arrMonth = (now.getMonth() + 1) % 12;
  const maxDaysArr = new Date(arrYear, arrMonth + 1, 0).getDate();
  const arrDay = Math.min(now.getDate(), maxDaysArr);
  const arrivalDateObj = new Date(arrYear, arrMonth, arrDay);

  // Departure: Exactly 3 months from today's date of next month (arrival date)
  const depTotalMonths = arrivalDateObj.getMonth() + 3;
  const depYear = arrivalDateObj.getFullYear() + Math.floor(depTotalMonths / 12);
  const depMonth = depTotalMonths % 12;
  const maxDaysDep = new Date(depYear, depMonth + 1, 0).getDate();
  const depDay = Math.min(arrivalDateObj.getDate(), maxDaysDep);
  const departureDateObj = new Date(depYear, depMonth, depDay);

  // Insurance Expiry: Standard 6 months validity from arrival date
  const insTotalMonths = arrivalDateObj.getMonth() + 6;
  const insYear = arrivalDateObj.getFullYear() + Math.floor(insTotalMonths / 12);
  const insMonth = insTotalMonths % 12;
  const maxDaysIns = new Date(insYear, insMonth + 1, 0).getDate();
  const insDay = Math.min(arrivalDateObj.getDate(), maxDaysIns);
  const insuranceDateObj = new Date(insYear, insMonth, insDay);

  const formatMMDDYYYY = (d: Date): string => {
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    const yyyy = d.getFullYear();
    return `${mm}/${dd}/${yyyy}`;
  };

  return {
    arrival_date: formatMMDDYYYY(arrivalDateObj),
    departure_date: formatMMDDYYYY(departureDateObj),
    insurance_valid_until: formatMMDDYYYY(insuranceDateObj),
    arrivalDateObj,
    departureDateObj,
    insuranceDateObj,
  };
}
