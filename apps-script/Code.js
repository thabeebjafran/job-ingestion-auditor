/** Entry point for direct messages to the Google Chat app. */
function onMessage(event) {
  console.log('Incoming Chat onMessage event:', JSON.stringify(event));

  try {
    const rawText = extractRawText_(event);
    if (!rawText) {
      console.log('No text found in event payload');
      return { text: '👋 Paste a job posting and I will audit it and prepare your tailored application.' };
    }

    console.log('Auditing job text (length: ' + rawText.length + ' chars)...');
    const auditedData = callReasoningEngine(rawText);
    
    // Save audited metadata reliably for Apply / Reject interactive actions
    const leadId = 'lead_' + Utilities.getUuid().replace(/-/g, '').substring(0, 12);
    try {
      PropertiesService.getUserProperties().setProperty(leadId, JSON.stringify(auditedData));
      CacheService.getScriptCache().put(leadId, JSON.stringify(auditedData), 21600);
    } catch (storeErr) {
      console.warn('Lead storage warning:', storeErr);
    }

    return buildChatAuditCard(auditedData, leadId);

  } catch (error) {
    console.error('onMessage error:', error && error.stack ? error.stack : error);
    return { text: '⚠️ Unable to audit this job: ' + userFacingError_(error) };
  }
}

/** Directly posts a message or CardV2 into a Google Chat space via Chat REST API. */
function sendChatMessageToSpace_(spaceName, payload, threadName) {
  try {
    const serviceAccount = JSON.parse(requireScriptProperty_('SERVICE_ACCOUNT_KEY'));
    const token = getServiceAccountAccessToken(serviceAccount);
    
    const url = 'https://chat.googleapis.com/v1/' + spaceName + '/messages?messageReplyOption=REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD';
    const body = Object.assign({}, payload);
    if (threadName) {
      body.thread = { name: threadName };
    }
    
    console.log('Posting directly to Google Chat thread:', url);
    const response = UrlFetchApp.fetch(url, {
      method: 'post',
      contentType: 'application/json',
      headers: {
        Authorization: 'Bearer ' + token
      },
      payload: JSON.stringify(body),
      muteHttpExceptions: true
    });
    const code = response.getResponseCode();
    const respText = response.getContentText();
    console.log('Google Chat REST API response code:', code, 'body:', respText);
  } catch (err) {
    console.error('Failed to post directly to Google Chat REST API:', err);
  }
}

/** Extracts message text across all Google Workspace Add-on and Chat event schemas. */
function extractRawText_(event) {
  if (!event) return '';
  
  if (event.chat && event.chat.messagePayload && event.chat.messagePayload.message) {
    const msg = event.chat.messagePayload.message;
    if (msg.text && msg.text.trim()) return msg.text.trim();
    if (msg.argumentText && msg.argumentText.trim()) return msg.argumentText.trim();
    if (msg.formattedText && msg.formattedText.trim()) return msg.formattedText.trim();
  }

  if (event.message) {
    if (event.message.text && event.message.text.trim()) return event.message.text.trim();
    if (event.message.argumentText && event.message.argumentText.trim()) return event.message.argumentText.trim();
    if (event.message.formattedText && event.message.formattedText.trim()) return event.message.formattedText.trim();
  }

  if (event.commonEventObject && event.commonEventObject.parameters && event.commonEventObject.parameters.rawText) {
    return event.commonEventObject.parameters.rawText;
  }

  return '';
}

/** Entry point when app is added to a space or direct 1:1 chat is opened (GCP Trigger: onAddedToSpace / onAddToSpace). */
function onAddedToSpace(event) {
  console.log('Incoming onAddedToSpace event:', JSON.stringify(event));
  return {
    action: {
      navigations: [
        {
          pushCard: {
            header: {
              title: 'Job Auditor Bot',
              subtitle: 'Tailored Job Applications & Verification'
            },
            sections: [
              {
                widgets: [
                  {
                    textParagraph: {
                      text: '👋 Hi! Paste any raw job posting in this chat, and I will audit its legitimacy, match your tech stack, check visa sponsorship, and record it in your application tracker.'
                    }
                  }
                ]
              }
            ]
          }
        }
      ]
    }
  };
}

function onAddToSpace(event) {
  return onAddedToSpace(event);
}

/** Entry point when app is removed from a space. */
function onRemovedFromSpace(event) {
  console.log('Bot removed from space:', JSON.stringify(event));
}

function onRemoveFromSpace(event) {
  return onRemovedFromSpace(event);
}

/** Entry point for slash/app commands. */
function onAppCommand(event) {
  console.log('Incoming onAppCommand event:', JSON.stringify(event));
  return onAddedToSpace(event);
}

/** Universal card click handlers. */
function onCardClick(event) {
  return onCardButtonClick(event);
}

function onCardClicked(event) {
  return onCardButtonClick(event);
}

function onCustomAction(event) {
  return onCardButtonClick(event);
}

function extractEventParams_(event) {
  const result = {};
  function ingest(source) {
    if (!source) return;
    if (Array.isArray(source)) {
      source.forEach(function(item) {
        if (item && item.key) result[item.key] = item.value;
      });
    } else if (typeof source === 'object') {
      Object.keys(source).forEach(function(k) {
        result[k] = source[k];
      });
    }
  }

  ingest(event && event.commonEventObject && event.commonEventObject.parameters);
  ingest(event && event.actionParameters);
  ingest(event && event.parameters);
  ingest(event && event.action && event.action.parameters);
  ingest(event && event.chat && event.chat.buttonClickedPayload && event.chat.buttonClickedPayload.action && event.chat.buttonClickedPayload.action.parameters);
  ingest(event && event.chat && event.chat.buttonClickedPayload && event.chat.buttonClickedPayload.parameters);

  return result;
}

/** Calls Vertex AI Gemini 2.0 Flash directly via REST API for sub-second audit response. */
function callReasoningEngine(rawJobText) {
  const serviceAccount = JSON.parse(requireScriptProperty_('SERVICE_ACCOUNT_KEY'));
  const projectId = serviceAccount.project_id || 'job-auditor-1787020056';
  const region = PropertiesService.getScriptProperties().getProperty('VERTEX_AI_REGION') || 'us-central1';
  const token = getServiceAccountAccessToken(serviceAccount);

  const endpoint = 'https://' + region + '-aiplatform.googleapis.com/v1/projects/' +
    projectId + '/locations/' + region + '/publishers/google/models/gemini-2.5-flash:generateContent';

  const systemInstruction = 
    'You are a senior technical career auditor for Thabeeb Jafran (Dubai, MIS graduate, SQL, Power BI, Tableau, GenAI, 5+ yrs exp).\n' +
    'Analyze this job lead. Flag scam risk if free @gmail.com used for corporate firm. ' +
    'Extract tech stack, contacts, visa context. Write 1-sentence note, tailored email body (<120 words, executive tone, no sign-off), and WhatsApp message (<60 words).\n' +
    'Return ONLY valid JSON matching this schema:\n' +
    '{"company_name": "string", "role_title": "string", "is_scam": boolean, "legitimacy_score": number, "visa_sponsorship": "string", "audit_notes": "string", "tech_stack_match": ["string"], "contact_email": "string", "contact_phone": "string", "career_url": "string", "tailored_email_subject": "string", "tailored_email_body": "string", "tailored_whatsapp_message": "string"}';

  const payload = {
    contents: [
      {
        role: 'user',
        parts: [
          {
            text: systemInstruction + '\n\nJob Posting:\n' + String(rawJobText).substring(0, 4000)
          }
        ]
      }
    ],
    generationConfig: {
      responseMimeType: 'application/json',
      temperature: 0.1,
      maxOutputTokens: 1024,
      thinkingConfig: {
        thinkingBudget: 0
      }
    }
  };

  const response = UrlFetchApp.fetch(endpoint, {
    method: 'post',
    contentType: 'application/json',
    headers: {
      Authorization: 'Bearer ' + token
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });

  const statusCode = response.getResponseCode();
  const responseBody = response.getContentText();

  if (statusCode < 200 || statusCode >= 300) {
    throw new Error('Vertex AI call failed with status ' + statusCode + ': ' + truncate_(responseBody, 500));
  }

  const jsonResp = JSON.parse(responseBody);
  const rawOutputText = jsonResp.candidates && jsonResp.candidates[0] && jsonResp.candidates[0].content && jsonResp.candidates[0].content.parts && jsonResp.candidates[0].content.parts[0] && jsonResp.candidates[0].content.parts[0].text;
  
  if (!rawOutputText) {
    throw new Error('No candidate content returned from Vertex AI: ' + truncate_(responseBody, 500));
  }

  let clean = rawOutputText.trim();
  if (clean.startsWith('```')) {
    clean = clean.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  }

  return JSON.parse(clean);
}

/** Builds the Two-Button Google Chat Card in official cardsV2 format. */
function buildChatAuditCard(data, leadId) {
  const score = Number(data.legitimacy_score);
  const scorePercent = isFinite(score) ? Math.round(score * 100) : '100';
  const statusBadge = data.is_scam ? '⚠️ SCAM ALERT' : '✅ Verified (' + scorePercent + '%)';
  const company = String(data.company_name || 'Unknown Company');
  const role = String(data.role_title || 'Unknown Role');
  const headerTitle = role + ' @ ' + company;
  const headerSubtitle = statusBadge + ' | Visa: ' + String(data.visa_sponsorship || 'Unknown');
  const techStack = Array.isArray(data.tech_stack_match) ? data.tech_stack_match.join(', ') : 'None extracted';
  const notes = String(data.audit_notes || 'No extra notes.');
  const careerUrl = data.career_url ? String(data.career_url) : '';
  const email = data.contact_email ? String(data.contact_email) : '';
  const phone = data.contact_phone ? String(data.contact_phone) : '';

  let contactInfoText = '';
  if (email) contactInfoText += '<br><b>✉️ Recruiter Email:</b> ' + escapeHtml_(email);
  if (phone) contactInfoText += '<br><b>📱 Recruiter WhatsApp/Phone:</b> ' + escapeHtml_(phone);

  const fullTextSummary = '*' + headerTitle + '*\n' +
    statusBadge + ' | *Visa:* ' + String(data.visa_sponsorship || 'Unknown') + '\n\n' +
    '• *Tech Stack:* ' + techStack + '\n' +
    '• *Notes:* ' + notes + '\n' +
    (email ? '• *Recruiter Email:* ' + email + '\n' : '') +
    (phone ? '• *Recruiter Phone:* ' + phone + '\n' : '') +
    (careerUrl ? '• *Apply Link:* ' + careerUrl + '\n' : '') +
    '• *Action:* Choose Apply (logs to Sheet1 & drafts outreach) or Reject (archives).';

  const card = {
    header: {
      title: headerTitle,
      subtitle: headerSubtitle
    },
    sections: [
      {
        widgets: [
          {
            textParagraph: {
              text: '<b>Tech Stack:</b> ' + escapeHtml_(techStack) + 
                    '<br><b>Notes:</b> ' + escapeHtml_(notes) + 
                    (careerUrl ? '<br><b>Apply Link:</b> ' + escapeHtml_(careerUrl) : '') +
                    contactInfoText
            }
          },
          {
            buttonList: {
              buttons: [
                cardButton_('✅ Apply & Draft', 'Apply', leadId, company, role, careerUrl, email, phone),
                cardButton_('🗑️ Reject / Archive', 'Reject', leadId, company, role, careerUrl, email, phone)
              ]
            }
          }
        ]
      }
    ]
  };

  return {
    text: fullTextSummary,
    cardsV2: [
      {
        cardId: 'audit_card_' + leadId,
        card: card
      }
    ]
  };
}

/** Handles Apply and Reject button clicks with Gmail Draft & WhatsApp generation */
function onCardButtonClick(event) {
  console.log('Incoming onCardButtonClick event:', JSON.stringify(event));

  try {
    const params = extractEventParams_(event);
    const action = params.action || 'Apply';
    const leadId = params.leadId;

    // Retrieve persistent full lead metadata
    let leadData = {};
    if (leadId) {
      try {
        const stored = PropertiesService.getUserProperties().getProperty(leadId) ||
                       CacheService.getScriptCache().get(leadId);
        if (stored) leadData = JSON.parse(stored);
      } catch (cErr) {
        console.warn('Could not read lead metadata:', cErr);
      }
    }

    // Fallback to button parameters if storage empty
    if (!leadData.company_name) leadData.company_name = params.company || 'N/A';
    if (!leadData.role_title) leadData.role_title = params.role || 'N/A';
    if (!leadData.career_url) leadData.career_url = params.careerUrl || '';
    if (!leadData.contact_email) leadData.contact_email = params.email || '';
    if (!leadData.contact_phone) leadData.contact_phone = params.phone || '';

    // ======================== ACTION: REJECT ========================
    if (action === 'Reject') {
      logRejectedJob(leadData);
      return {
        actionResponse: { type: 'NEW_MESSAGE' },
        text: '🗑️ *Job Lead Archived:* ' + leadData.role_title + ' @ ' + leadData.company_name + 
              ' was moved to the *Rejected Leads* tab.\n\n_Sheet1 remains 100% clean._'
      };
    }

    // ======================== ACTION: APPLY ========================
    const rowIndex = logAppliedJob(leadData);
    let feedbackLines = [
      '✅ *Application Logged to Sheet1 (Row ' + rowIndex + '):* ' + leadData.role_title + ' @ ' + leadData.company_name
    ];

    // 1. If Recruiter Email is present -> Create Gmail Draft with Resume attached
    if (leadData.contact_email) {
      try {
        const resumeBlob = fetchResumeBlob_();
        const emailSubject = leadData.tailored_email_subject || ('Application: ' + leadData.role_title + ' – Thabeeb Jafran');
        const emailBody = leadData.tailored_email_body || 
          ('Dear ' + (leadData.company_name || 'Hiring') + ' Team,\n\nI am writing to express my strong interest in the ' + 
           leadData.role_title + ' position. With over 5 years of experience in data analytics, business intelligence, and process automation, I specialize in translating complex business requirements into scalable technology solutions.');

        try {
          const draftOptions = {
            from: 'contact@thabeebjafran.site'
          };
          if (resumeBlob) {
            draftOptions.attachments = [resumeBlob];
          }
          GmailApp.createDraft(leadData.contact_email, emailSubject, emailBody, draftOptions);
        } catch (fromErr) {
          console.warn('Could not set custom from address alias, using default:', fromErr);
          const defaultOptions = {};
          if (resumeBlob) {
            defaultOptions.attachments = [resumeBlob];
          }
          GmailApp.createDraft(leadData.contact_email, emailSubject, emailBody, defaultOptions);
        }

        feedbackLines.push(
          '✉️ *Gmail Draft Created:* Tailored application prepared for *' + leadData.contact_email + '* from *contact@thabeebjafran.site* with *ThabeebJafranResume.pdf* attached!\n👉 <https://mail.google.com/mail/#drafts|Open Gmail Drafts>'
        );
      } catch (gmailErr) {
        console.error('Failed to create Gmail draft:', gmailErr);
        feedbackLines.push('⚠️ *Gmail Draft Note:* ' + userFacingError_(gmailErr));
      }
    }

    // 2. If Recruiter Phone / WhatsApp is present -> Create 1-tap WhatsApp link
    if (leadData.contact_phone) {
      const cleanPhone = String(leadData.contact_phone).replace(/[^0-9+]/g, '');
      const waMsg = leadData.tailored_whatsapp_message || buildDefaultWhatsAppMsg_(leadData);
      const waUrl = 'https://wa.me/' + cleanPhone.replace('+', '') + '?text=' + encodeURIComponent(waMsg);

      feedbackLines.push(
        '📱 *Recruiter WhatsApp:* ' + leadData.contact_phone + '\n👉 <' + waUrl + '|Tap to Open WhatsApp & Send Pitch>'
      );
    }

    // 3. If neither email nor phone -> Provide direct career apply link
    if (!leadData.contact_email && !leadData.contact_phone) {
      if (leadData.career_url) {
        feedbackLines.push('🌐 *Apply Directly Online:* <' + leadData.career_url + '|' + leadData.career_url + '>');
      }
    }

    return {
      actionResponse: { type: 'NEW_MESSAGE' },
      text: feedbackLines.join('\n\n')
    };

  } catch (error) {
    console.error('onCardButtonClick error:', error && error.stack ? error.stack : error);
    return {
      actionResponse: { type: 'NEW_MESSAGE' },
      text: '⚠️ Unable to process action: ' + userFacingError_(error)
    };
  }
}

function cardButton_(text, action, leadId, company, role, careerUrl, email, phone) {
  return {
    text: text,
    onClick: {
      action: {
        function: 'onCardButtonClick',
        parameters: [
          { key: 'action', value: action },
          { key: 'leadId', value: String(leadId || '') },
          { key: 'company', value: String(company || '') },
          { key: 'role', value: String(role || '') },
          { key: 'careerUrl', value: String(careerUrl || '') },
          { key: 'email', value: String(email || '') },
          { key: 'phone', value: String(phone || '') }
        ]
      }
    }
  };
}


function buildDefaultEmailBody_(data) {
  return "Dear " + (data.company_name || 'Hiring') + " Team,\n\n" +
    "I am reaching out regarding the " + (data.role_title || 'open') + " position. With my background in Management Information Systems from SLIIT, Google Project Management certification, and hands-on experience delivering data analytics pipelines and operations coordination, I specialize in translating complex business requirements into automated solutions.\n\n" +
    "In my recent project delivery, I managed cross-functional workflows, engineered SQL/Power BI dashboards, and maintained 100% compliance. I am currently based in Dubai, UAE, and available for immediate joining.";
}

function buildDefaultWhatsAppMsg_(data) {
  return "Hello " + (data.company_name || '') + " Team,\n\n" +
    "• Thabeeb Jafran applying for " + (data.role_title || 'the role') + ".\n" +
    "• Dubai-based with immediate joining availability.\n" +
    "• Experienced in Agile project delivery, operations coordination (300-400 fleet operations), and analytics.\n" +
    "• Portfolio: https://public.tableau.com/profile/thabeebjafran\n" +
    "• Phone: +971 56 844 7304. Looking forward to connecting!";
}

function requireScriptProperty_(name) {
  const value = PropertiesService.getScriptProperties().getProperty(name);
  if (!value) throw new Error('Missing Script Property: ' + name);
  return value;
}

function truncate_(value, maxLength) {
  return String(value).slice(0, maxLength);
}

function userFacingError_(error) {
  return truncate_(error && error.message ? error.message : error, 500);
}

function escapeHtml_(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

/** Fetches the latest resume PDF directly from Google Drive */
function fetchResumeBlob_() {
  const resumeDriveId = PropertiesService.getScriptProperties().getProperty('RESUME_DRIVE_FILE_ID') || '1Jk4YyVJK0kC8R32LGyQdv5GyBVtbMPys';
  
  // 1. Direct Google Drive export download
  try {
    const downloadUrl = 'https://drive.google.com/uc?export=download&id=' + resumeDriveId;
    const response = UrlFetchApp.fetch(downloadUrl, { muteHttpExceptions: true });
    if (response.getResponseCode() === 200 && response.getBlob().getBytes().length > 1000) {
      return response.getBlob().setName('ThabeebJafranResume.pdf').setContentType('application/pdf');
    }
  } catch (urlErr) {
    console.warn('UrlFetchApp drive download note:', urlErr);
  }

  // 2. DriveApp fallback
  try {
    return DriveApp.getFileById(resumeDriveId).getBlob().setName('ThabeebJafranResume.pdf');
  } catch (driveErr) {
    console.warn('DriveApp note:', driveErr);
  }

  return null;
}
