const APPLICATION_LOG_SHEET = PropertiesService.getScriptProperties().getProperty('APPLICATION_LOG_SHEET_NAME') || 'Sheet1';
const REJECTED_LOG_SHEET = 'Rejected Leads';

/** Logs an applied job to Sheet1 */
function logAppliedJob(data) {
  const sheet = getApplicationLogSheet_(APPLICATION_LOG_SHEET);
  ensureMainHeaders_(sheet);

  const now = new Date();
  const dateAdded = Utilities.formatDate(now, 'Asia/Dubai', 'yyyy-MM-dd');
  const followUpDate = Utilities.formatDate(new Date(now.getTime() + 3 * 24 * 60 * 60 * 1000), 'Asia/Dubai', 'yyyy-MM-dd');

  const score = Number(data.legitimacy_score);
  const scorePercent = isFinite(score) ? Math.round(score * 100) : 100;
  const scorePrefix = data.is_scam ? '⚠️ SCAM - ' : '✅ ' + scorePercent + '% - ';
  const auditNotesCombined = scorePrefix + (data.audit_notes || 'No extra notes.');

  const rawVisa = String(data.visa_sponsorship || '').toLowerCase();
  const visaDropdownValue = (rawVisa.includes('avail') || rawVisa.includes('sponsor') || rawVisa.includes('yes') || rawVisa.includes('provid') || rawVisa.includes('req'))
    ? 'Requires Sponsorship'
    : 'Not Required';

  sheet.appendRow([
    data.company_name || 'N/A',
    data.role_title || 'N/A',
    data.career_url || 'N/A',
    'Applied', // Marked as Applied immediately
    visaDropdownValue,
    dateAdded,
    followUpDate,
    (data.tech_stack_match || []).join(', '),
    auditNotesCombined
  ]);

  return sheet.getLastRow();
}

/** Logs a rejected lead to a separate 'Rejected Leads' tab so Sheet1 stays clean */
function logRejectedJob(data) {
  const sheet = getApplicationLogSheet_(REJECTED_LOG_SHEET);
  if (sheet.getLastRow() === 0) {
    sheet.appendRow([
      'Company',
      'Role Title',
      'Apply Link',
      'Status',
      'Visa Status',
      'Date Rejected',
      'Audit Notes'
    ]);
  }

  const now = new Date();
  const dateRejected = Utilities.formatDate(now, 'Asia/Dubai', 'yyyy-MM-dd');

  const score = Number(data.legitimacy_score);
  const scorePercent = isFinite(score) ? Math.round(score * 100) : 100;
  const scorePrefix = data.is_scam ? '⚠️ SCAM - ' : '✅ ' + scorePercent + '% - ';
  const auditNotesCombined = scorePrefix + (data.audit_notes || 'No extra notes.');

  sheet.appendRow([
    data.company_name || 'N/A',
    data.role_title || 'N/A',
    data.career_url || 'N/A',
    'Rejected',
    data.visa_sponsorship || 'Not Specified',
    dateRejected,
    auditNotesCombined
  ]);

  return sheet.getLastRow();
}

function logAuditedJob(data) {
  return logAppliedJob(data);
}

function ensureMainHeaders_(sheet) {
  if (sheet.getLastRow() === 0) {
    sheet.appendRow([
      'Company',
      'Role Title',
      'Apply Link',
      'Status',
      'Visa Status',
      'Date Added',
      'Follow-up Date',
      'Tech Stack',
      'Audit Notes'
    ]);
  }
}

function updateJobStatus(rowIndex, status) {
  const sheet = getApplicationLogSheet_(APPLICATION_LOG_SHEET);
  if (rowIndex < 2 || rowIndex > sheet.getLastRow()) throw new Error('Application-log row was not found: ' + rowIndex);
  sheet.getRange(rowIndex, 4).setValue(status);
}

function getApplicationLogSheet_(tabName) {
  const sheetName = tabName || PropertiesService.getScriptProperties().getProperty('APPLICATION_LOG_SHEET_NAME') || 'Sheet1';
  
  // 1. If script is attached directly to the Spreadsheet (Extensions > Apps Script)
  let book = SpreadsheetApp.getActiveSpreadsheet();

  // 2. Open via APPLICATION_LOG_SPREADSHEET_ID property
  if (!book) {
    const spreadsheetId = PropertiesService.getScriptProperties().getProperty('APPLICATION_LOG_SPREADSHEET_ID');
    if (spreadsheetId) {
      try {
        book = SpreadsheetApp.openById(spreadsheetId);
      } catch (openErr) {
        console.warn('Could not open spreadsheet by ID:', openErr);
      }
    }
  }

  // 3. Auto-discover or create tracker spreadsheet in Google Drive
  if (!book) {
    try {
      const files = DriveApp.getFilesByName('Job Ingestion & Application Tracker');
      if (files.hasNext()) {
        book = SpreadsheetApp.open(files.next());
        PropertiesService.getScriptProperties().setProperty('APPLICATION_LOG_SPREADSHEET_ID', book.getId());
      } else {
        book = SpreadsheetApp.create('Job Ingestion & Application Tracker');
        PropertiesService.getScriptProperties().setProperty('APPLICATION_LOG_SPREADSHEET_ID', book.getId());
      }
    } catch (dErr) {
      console.warn('Drive auto-discover warning:', dErr);
    }
  }

  if (!book) {
    throw new Error('Spreadsheet tracker could not be accessed. Please ensure Google Drive permissions are enabled.');
  }

  return book.getSheetByName(sheetName) || book.insertSheet(sheetName);
}

/** Checks if a job has already been logged to prevent duplicate audits. */
function isJobAlreadyLogged_(company, role, careerUrl) {
  try {
    const sheet = getApplicationLogSheet_();
    const lastRow = sheet.getLastRow();
    if (lastRow < 2) return false;

    // Fetch Company (Col 1), Role (Col 2), and Apply Link (Col 3)
    const data = sheet.getRange(2, 1, lastRow - 1, 3).getValues();
    const compLower = String(company || '').trim().toLowerCase();
    const roleLower = String(role || '').trim().toLowerCase();
    const urlClean = String(careerUrl || '').trim().toLowerCase();

    for (let i = 0; i < data.length; i++) {
      const rowCompany = String(data[i][0] || '').trim().toLowerCase();
      const rowRole = String(data[i][1] || '').trim().toLowerCase();
      const rowUrl = String(data[i][2] || '').trim().toLowerCase();

      // Check URL match (if available)
      if (urlClean && rowUrl && (urlClean.includes(rowUrl) || rowUrl.includes(urlClean))) {
        return true;
      }
      // Check Company + Role match
      if (compLower && roleLower && rowCompany === compLower && rowRole === roleLower) {
        return true;
      }
    }
    return false;
  } catch (err) {
    console.warn('Deduplication check error:', err);
    return false;
  }
}
