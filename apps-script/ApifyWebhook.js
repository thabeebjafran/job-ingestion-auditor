/**
 * Webhook endpoints for automated job ingestion from Apify scrapers.
 */

/** HTTP GET: Health check endpoint */
function doGet(e) {
  return ContentService.createTextOutput(JSON.stringify({
    status: 'ok',
    service: 'Job Ingestion Auditor Webhook Receiver',
    timestamp: new Date().toISOString()
  })).setMimeType(ContentService.MimeType.JSON);
}

/** HTTP POST: Apify Run Succeeded Webhook Receiver */
function doPost(e) {
  console.log('Incoming Apify Webhook POST:', e && e.postData ? e.postData.contents : 'No postData');
  
  try {
    let payload = {};
    if (e && e.postData && e.postData.contents) {
      try {
        payload = JSON.parse(e.postData.contents);
      } catch (jsonErr) {
        console.warn('Failed to parse raw postData contents:', jsonErr);
      }
    }

    // 0. Handle interactive card button clicks forwarded from Cloud Function
    if (payload.action === 'card_action') {
      const buttonAction = payload.buttonAction || 'Apply';
      const leadData = {
        company_name: payload.company || 'N/A',
        role_title: payload.role || 'N/A',
        contact_email: payload.email || '',
        contact_phone: payload.phone || '',
        career_url: payload.career_url || '',
        tailored_email_subject: payload.subject || ('Application: ' + (payload.role || 'Role') + ' – Thabeeb Jafran'),
        tailored_email_body: payload.body || '',
        tailored_whatsapp_message: payload.wa_msg || ''
      };

      if (buttonAction === 'Reject') {
        logRejectedJob(leadData);
      } else {
        logAppliedJob(leadData);
        if (leadData.contact_email) {
          try {
            const resumeBlob = fetchResumeBlob_();
            const draftOptions = {};
            if (resumeBlob) draftOptions.attachments = [resumeBlob];
            GmailApp.createDraft(leadData.contact_email, leadData.tailored_email_subject, leadData.tailored_email_body, draftOptions);
          } catch (dErr) {
            console.error('Failed to create draft from card_action:', dErr);
          }
        }
      }
      return ContentService.createTextOutput(JSON.stringify({ status: 'success' })).setMimeType(ContentService.MimeType.JSON);
    }

    const defaultSpace = PropertiesService.getScriptProperties().getProperty('DEFAULT_CHAT_SPACE_NAME') || 'spaces/ohJgDKAAAAE';
    const apifyToken = PropertiesService.getScriptProperties().getProperty('APIFY_API_TOKEN') || '';

    let items = [];

    // 1. Check if raw dataset items array is passed directly in POST body
    if (Array.isArray(payload)) {
      items = payload;
    } else if (payload.items && Array.isArray(payload.items)) {
      items = payload.items;
    } else {
      // 2. Extract dataset ID from standard Apify webhook payload
      const datasetId = (payload.resource && payload.resource.defaultDatasetId) ||
                        (payload.eventData && payload.eventData.defaultDatasetId) ||
                        (payload.defaultDatasetId);

      if (datasetId) {
        console.log('Fetching dataset items from Apify dataset ID:', datasetId);
        items = fetchApifyDatasetItems_(datasetId, apifyToken);
      }
    }

    if (!items || items.length === 0) {
      console.log('No job items found in webhook payload.');
      return ContentService.createTextOutput(JSON.stringify({
        status: 'success',
        message: 'No job items to process.'
      })).setMimeType(ContentService.MimeType.JSON);
    }

    console.log('Processing ' + items.length + ' scraped job items from Apify...');
    const results = processScrapedJobsBatch_(items, defaultSpace);

    return ContentService.createTextOutput(JSON.stringify({
      status: 'success',
      totalItems: items.length,
      processed: results.auditedCount,
      skippedDuplicates: results.skippedCount
    })).setMimeType(ContentService.MimeType.JSON);

  } catch (error) {
    console.error('doPost Apify webhook error:', error && error.stack ? error.stack : error);
    return ContentService.createTextOutput(JSON.stringify({
      status: 'error',
      message: error && error.message ? error.message : String(error)
    })).setMimeType(ContentService.MimeType.JSON);
  }
}

/** Fetches items from Apify Dataset API */
function fetchApifyDatasetItems_(datasetId, token) {
  let url = 'https://api.apify.com/v2/datasets/' + datasetId + '/items?limit=15&desc=true';
  if (token) {
    url += '&token=' + encodeURIComponent(token);
  }

  const response = UrlFetchApp.fetch(url, {
    method: 'get',
    muteHttpExceptions: true
  });

  if (response.getResponseCode() !== 200) {
    console.warn('Apify dataset fetch returned HTTP ' + response.getResponseCode() + ': ' + response.getContentText());
    return [];
  }

  try {
    return JSON.parse(response.getContentText());
  } catch (err) {
    console.error('Failed to parse Apify dataset response:', err);
    return [];
  }
}

/** Processes a batch of scraped job items through Vertex AI, Google Sheets, and Google Chat */
function processScrapedJobsBatch_(items, targetSpace) {
  let auditedCount = 0;
  let skippedCount = 0;

  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    if (!item) continue;

    // Normalize field names across various Apify job scrapers (LinkedIn, Indeed, Glassdoor)
    const company = item.companyName || item.company || item.company_name || item.employerName || 'Unknown Company';
    const role = item.title || item.jobTitle || item.positionName || item.role || 'Unknown Role';
    const location = item.location || item.formattedLocation || item.jobLocation || 'Not Specified';
    const applyUrl = item.jobUrl || item.applyUrl || item.link || item.url || '';
    const description = item.description || item.descriptionHtml || item.snippet || item.jobDescription || '';

    // Check deduplication
    if (isJobAlreadyLogged_(company, role, applyUrl)) {
      console.log('Skipping duplicate job lead: ' + role + ' @ ' + company);
      skippedCount++;
      continue;
    }

    // Build raw job lead text for Vertex AI Reasoning Engine
    const rawJobLead = [
      'Company: ' + company,
      'Role: ' + role,
      'Location: ' + location,
      'Apply URL: ' + applyUrl,
      'Job Details / Requirements:\n' + description.substring(0, 1500)
    ].join('\n');

    console.log('Auditing Apify job lead [' + (i + 1) + '/' + items.length + ']: ' + role + ' @ ' + company);

    try {
      const auditedData = callReasoningEngine(rawJobLead);
      
      // Generate unique lead ID and cache metadata for two-button action handling
      const leadId = 'lead_' + Utilities.getUuid().replace(/-/g, '').substring(0, 12);
      try {
        CacheService.getScriptCache().put(leadId, JSON.stringify(auditedData), 21600);
      } catch (cErr) {
        console.warn('CacheService warning in ApifyWebhook:', cErr);
      }

      // Deliver interactive 2-Button Card to Google Chat
      if (targetSpace) {
        const cardResponse = buildChatAuditCard(auditedData, leadId);
        sendChatMessageToSpace_(targetSpace, cardResponse);
      }

      auditedCount++;
    } catch (auditErr) {
      console.error('Failed to audit Apify job lead:', auditErr);
    }
  }

  return {
    auditedCount: auditedCount,
    skippedCount: skippedCount
  };
}
