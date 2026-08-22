import os
import json
import requests
import urllib.parse
import html
import google.auth
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from google.oauth2 import service_account
from google.auth.transport.requests import Request as AuthRequest
from google import genai
from google.genai import types
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI()

# Load candidate profile
PROFILE_PATH = os.path.join(os.path.dirname(__file__), 'profile', 'thabeeb_profile_context.txt')
if os.path.exists(PROFILE_PATH):
    with open(PROFILE_PATH, 'r', encoding='utf-8') as pf:
        CANDIDATE_PROFILE = pf.read()
else:
    CANDIDATE_PROFILE = 'Thabeeb Jafran - Data Analyst, Business Analyst & MIS Graduate based in Dubai'

# Credentials setup
CREDS_PATH = os.path.join(os.path.dirname(__file__), 'credentials.json')
PROJECT_ID = os.environ.get('GOOGLE_CLOUD_PROJECT', 'job-auditor-bot-2026')
REGION = 'us-central1'
APPS_SCRIPT_WEBHOOK = 'https://script.google.com/macros/s/AKfycbwz8aZEzDyX-R4su8rDX5cYVYt-FJCT7itNfbEagPAI6FczsfzLvgj6TK8lEn7sXEiunw/exec'

class JobAuditOutput(BaseModel):
    company_name: str
    role_title: str
    legitimacy_score: float
    is_scam: bool
    visa_sponsorship: str
    tech_stack_match: List[str]
    career_url: Optional[str]
    audit_notes: str
    contact_email: Optional[str]
    contact_phone: Optional[str]
    tailored_angle: Optional[str]
    tailored_email_subject: Optional[str]
    tailored_email_body: Optional[str]
    tailored_whatsapp_message: Optional[str]

SPREADSHEET_ID = '1KG_3jOcpVtSpOJ3XYBzKz8tlvyrwq3r_1NAKde_ujFs'

def get_google_access_token():
    creds, _ = google.auth.default(scopes=[
        'https://www.googleapis.com/auth/chat.bot',
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/cloud-platform'
    ])
    creds.refresh(AuthRequest())
    return creds.token

def append_to_sheet(tab_name: str, row_values: list):
    try:
        token = get_google_access_token()
        url = f'https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values/{tab_name}!A:I:append?valueInputOption=USER_ENTERED'
        res = requests.post(url, headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}, json={'values': [row_values]}, timeout=10)
        print(f"Append to {tab_name} response ({res.status_code}):", res.text)
        return res.status_code == 200
    except Exception as e:
        print(f"Error appending to {tab_name}:", e)
        return False

def post_chat_message(space_name: str, payload: dict):
    token = get_google_access_token()
    url = f'https://chat.googleapis.com/v1/{space_name}/messages'
    return requests.post(url, headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}, json=payload, timeout=15)

def call_gemini_audit(raw_job_text: str = '', image_bytes: bytes = None, mime_type: str = 'image/png') -> dict:
    if os.path.exists(CREDS_PATH):
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = CREDS_PATH
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=REGION)

    prompt = f"""You are the Strategic Career Agent and Technical Recruiter for Thabeeb Jafran.

CANDIDATE DOSSIER (Resume & Master Technical Portfolio):
----------------------------------------
{CANDIDATE_PROFILE}
----------------------------------------

TARGET JOB POSTING TO AUDIT & TARGET (From Image Screenshot and/or Text):
----------------------------------------
{raw_job_text[:4000]}
----------------------------------------

INSTRUCTIONS:
1. Audit: Read and extract all job details from the provided image screenshot and/or text. Extract company_name, role_title, contact_email, contact_phone, career_url, visa_sponsorship, tech_stack_match. Evaluate scam risk (flag if free personal email like @gmail/@yahoo used for major enterprise brands). Write a concise 1-2 sentence audit_notes.
2. Tailored Email Subject (tailored_email_subject):
   - Format: 'Application: [Role Title] – Thabeeb Jafran' or 'Thabeeb Jafran – [Role Title] | [Key Tech Stack Match]'
3. Tailored Email Pitch (tailored_email_body):
   - Write a short, high-impact executive outreach message (<140 words, 2-3 brief paragraphs, executive tone, NO sign-off/signature as native Gmail signature attaches automatically).
   - DIRECT VALUE & PROJECT DEMONSTRATION: Show how their specific job requirements directly map to Thabeeb's background. Detail the most relevant project from the Master Portfolio with concrete metrics (e.g. $55.3M revenue tracking with PostgreSQL & DAX, +11.5% pricing optimization with Python, IBM ML attrition risk modeling, n8n/Gemini AI automation pipelines, or operations rollout driving +20% sales).
   - Let the concrete project evidence prove capability.
   - End with: 'My resume is attached for your review. Please let me know if you would like me to share further project walkthroughs or discuss how I can support [Company Name].'
4. Tailored WhatsApp Message (tailored_whatsapp_message):
   - Write a concise, respectful, and high-impact message (<50 words).
   - Structure: 'Hello! I am Thabeeb Jafran. Reviewing your [Role Title] opening, my background in [Key Matching Stack] directly aligns with your requirements — in my [Matching Project Name] project, I delivered [Key Metric/Impact] using [Tech Stack]. Happy to share further project details if you would like to connect.'
   - Do NOT include any links or informal language. Keep it courteous, professional, and data-backed.
"""
    contents = []
    if image_bytes:
        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        contents.append(image_part)
    contents.append(prompt)

    res = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type='application/json',
            response_schema=JobAuditOutput,
            max_output_tokens=1024,
            temperature=0.1,
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        )
    )
    return json.loads(res.text)

def build_card_obj(data: dict, sheet_status: str, space_name: str = '') -> dict:
    company = html.escape(str(data.get('company_name') or 'Target Company'))
    role = html.escape(str(data.get('role_title') or 'Open Position'))
    is_scam = data.get('is_scam', False)
    visa = html.escape(str(data.get('visa_sponsorship') or 'Not Specified'))
    notes = html.escape(str(data.get('audit_notes') or 'Audit completed.'))
    tech_stack = html.escape(', '.join(data.get('tech_stack_match') or []))
    email = html.escape(str(data.get('contact_email') or ''))
    phone = html.escape(str(data.get('contact_phone') or ''))
    career_url = html.escape(str(data.get('career_url') or ''))
    
    raw_subject = data.get('tailored_email_subject') or f'Application: {data.get("role_title") or "Role"} – Thabeeb Jafran'
    raw_body = data.get('tailored_email_body') or ''
    raw_wa = data.get('tailored_whatsapp_message') or ''

    # Clean pitch bodies without extra links or duplicate signatures
    full_email_body = raw_body.strip()
    full_wa_body = raw_wa.strip()

    scam_header = '⚠️ SCAM ALERT' if is_scam else '✅ LEGITIMATE'
    subtitle = f'{scam_header} | Visa: {visa} | 📊 {sheet_status}'

    action_buttons = []
    
    # 1. Compose Button (Universal link: Native Gmail App on Mobile, Gmail Web Compose on Laptop)
    if email:
        import urllib.parse
        params = urllib.parse.urlencode({
            'to': email,
            'su': raw_subject,
            'body': full_email_body
        })
        universal_url = f"https://job-auditor-service-709855928444.us-central1.run.app/compose?{params}"
        action_buttons.append({
            'text': '✉️ Compose',
            'onClick': {
                'openLink': {
                    'url': universal_url
                }
            }
        })

    # 2. WhatsApp Button (if phone / WhatsApp number is detected)
    if phone:
        clean_phone = ''.join(c for c in phone if c.isdigit() or c == '+')
        wa_url = f'https://wa.me/{clean_phone.replace("+", "")}?text=' + requests.utils.quote(full_wa_body)
        action_buttons.append({
            'text': '📱 WhatsApp',
            'onClick': {
                'openLink': {
                    'url': wa_url
                }
            }
        })

    # 3. Apply Online Button (if career application URL exists)
    if career_url:
        action_buttons.append({
            'text': '🌐 Apply Online',
            'onClick': {
                'openLink': {
                    'url': career_url
                }
            }
        })

    # 4. Fallback search button if no direct contact or apply link was detected
    if not action_buttons:
        import urllib.parse
        search_query = urllib.parse.quote(f"{data.get('company_name', '')} {data.get('role_title', '')} Dubai careers apply")
        action_buttons.append({
            'text': '🌐 View / Apply on Web',
            'onClick': {
                'openLink': {
                    'url': f'https://www.google.com/search?q={search_query}'
                }
            }
        })

    # 5. Clear Gateway Button (Universal 1-Tap)
    clear_url = f"https://job-auditor-service-709855928444.us-central1.run.app/clear?company={urllib.parse.quote(str(data.get('company_name') or 'Company'))}&role={urllib.parse.quote(str(data.get('role_title') or 'Role'))}&space={urllib.parse.quote(space_name)}"
    action_buttons.append({
        'text': '✅ Applied & Clear',
        'onClick': {
            'openLink': {
                'url': clear_url
            }
        }
    })

    widgets = [
        {
            'textParagraph': {
                'text': f'<b>Tech Stack:</b> {tech_stack}<br><b>Notes:</b> {notes}' +
                        (f'<br><b>✉️ Recruiter Email:</b> {email}' if email else '') +
                        (f'<br><b>📱 Recruiter Phone:</b> {phone}' if phone else '') +
                        (f'<br><b>🌐 Apply Link:</b> {career_url}' if career_url else '')
            }
        },
        {
            'buttonList': {
                'buttons': action_buttons
            }
        }
    ]

    return {
        'header': {
            'title': f'{role} @ {company}',
            'subtitle': subtitle
        },
        'sections': [{'widgets': widgets}]
    }

@app.get("/")
async def health_check():
    return {"status": "healthy", "service": "Job Auditor FastAPI"}

@app.get("/compose")
async def universal_compose(request: Request, to: str = '', su: str = '', body: str = ''):
    import urllib.parse
    user_agent = request.headers.get('user-agent', '').lower()
    is_mobile = any(m in user_agent for m in ['mobile', 'android', 'iphone', 'ipad', 'ipod'])
    
    if is_mobile:
        encoded_su = urllib.parse.quote(su, safe='')
        encoded_body = urllib.parse.quote(body, safe='')
        mailto_url = f"mailto:{to}?subject={encoded_su}&body={encoded_body}"
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Opening Gmail...</title>
    <script>
        window.location.href = {json.dumps(mailto_url)};
        setTimeout(function() {{
            window.location.href = {json.dumps(f"https://mail.google.com/mail/?view=cm&fs=1&to={to}&su=" + urllib.parse.quote(su) + "&body=" + urllib.parse.quote(body))};
        }}, 2000);
    </script>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; text-align: center; padding: 40px; color: #202124;">
    <h3>Opening Gmail App...</h3>
    <p style="color: #5f6368;">If your email app did not open automatically, tap below:</p>
    <p><a href="{mailto_url}" style="display:inline-block; padding: 12px 24px; background:#0B57D0; color:white; border-radius:24px; text-decoration:none; font-weight:bold; font-size:16px;">Open Gmail App</a></p>
</body>
</html>"""
        return HTMLResponse(content=html_content)
    else:
        # Desktop / Laptop Web -> Redirect directly to Gmail Web Compose with prefilled draft
        gmail_web_url = f"https://mail.google.com/mail/?view=cm&fs=1&to={to}&su={urllib.parse.quote(su)}&body={urllib.parse.quote(body)}"
        return RedirectResponse(url=gmail_web_url)

CLEARED_LEAD_KEYS = set()

@app.get("/clear")
async def clear_gateway(request: Request, company: str = 'Company', role: str = 'Role', space: str = ''):
    lead_key = f"{space.strip()}:{company.strip().lower()}:{role.strip().lower()}"
    
    # Only post once per lead (deduplicate multiple clicks)
    if space and lead_key not in CLEARED_LEAD_KEYS:
        CLEARED_LEAD_KEYS.add(lead_key)
        try:
            post_chat_message(space, {
                'text': f'~~{role} @ {company}~~ • ✅ *Applied & Cleared!*'
            })
            print(f"Posted clear confirmation for {role} @ {company} to space {space}")
        except Exception as e:
            print("Error posting clear message to space:", e)
    else:
        print(f"Duplicate clear click ignored for {lead_key}")
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Application Cleared</title>
    <style>
        body {{
            background-color: #0f172a;
            color: #f8fafc;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
            padding: 20px;
            box-sizing: border-box;
            text-align: center;
        }}
        .card {{
            background: #1e293b;
            padding: 32px;
            border-radius: 16px;
            max-width: 420px;
            width: 100%;
            border: 1px solid #334155;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
        }}
        .icon {{
            font-size: 48px;
            margin-bottom: 12px;
        }}
        h2 {{
            margin: 0 0 8px 0;
            color: #38bdf8;
            font-size: 20px;
        }}
        p {{
            color: #94a3b8;
            font-size: 14px;
            line-height: 1.5;
            margin: 0 0 20px 0;
        }}
        .btn {{
            display: inline-block;
            padding: 10px 20px;
            background: #0284c7;
            color: white;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            font-size: 14px;
        }}
    </style>
    <script>
        setTimeout(function() {{
            window.close();
        }}, 1800);
    </script>
</head>
<body>
    <div class="card">
        <div class="icon">✅</div>
        <h2>Application Cleared!</h2>
        <p><b>{html.escape(role)}</b> at <b>{html.escape(company)}</b> has been cleared and completed.</p>
        <a href="javascript:window.close()" class="btn">Close Window</a>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html_content)

@app.get("/setup-dropdowns")
async def setup_dropdowns():
    try:
        token = get_google_access_token()
        meta_url = f'https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}'
        meta_res = requests.get(meta_url, headers={'Authorization': f'Bearer {token}'})
        meta = meta_res.json()
        sheet1_id = 0
        for s in meta.get('sheets', []):
            if s.get('properties', {}).get('title') == 'Sheet1':
                sheet1_id = s['properties']['sheetId']
                break

        # Auto-fix any typo 'Coudn't' in existing rows
        try:
            d_val_url = f'https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values/Sheet1!D2:D'
            d_vals_res = requests.get(d_val_url, headers={'Authorization': f'Bearer {token}'}).json()
            rows = d_vals_res.get('values', [])
            fixed = False
            for r in rows:
                if r and r[0] == "Coudn't":
                    r[0] = "Couldn't"
                    fixed = True
            if fixed:
                requests.put(f'https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values/Sheet1!D2:D?valueInputOption=USER_ENTERED', headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}, json={'values': rows})
        except Exception as fix_err:
            print("Error fixing typos:", fix_err)

        reqs = [
            {
                'setDataValidation': {
                    'range': {
                        'sheetId': sheet1_id,
                        'startRowIndex': 1,
                        'endRowIndex': 10000,
                        'startColumnIndex': 3,
                        'endColumnIndex': 4
                    },
                    'rule': {
                        'condition': {
                            'type': 'ONE_OF_LIST',
                            'values': [
                                {'userEnteredValue': 'Applied'},
                                {'userEnteredValue': 'Couldn\'t'},
                                {'userEnteredValue': 'Try Again'},
                                {'userEnteredValue': 'Interviewing'},
                                {'userEnteredValue': 'Offered'},
                                {'userEnteredValue': 'Rejected'},
                                {'userEnteredValue': 'Accepted'}
                            ]
                        },
                        'showCustomUi': True,
                        'strict': False
                    }
                }
            },
            {
                'setDataValidation': {
                    'range': {
                        'sheetId': sheet1_id,
                        'startRowIndex': 1,
                        'endRowIndex': 10000,
                        'startColumnIndex': 4,
                        'endColumnIndex': 5
                    },
                    'rule': {
                        'condition': {
                            'type': 'ONE_OF_LIST',
                            'values': [
                                {'userEnteredValue': 'Requires Sponsorship'},
                                {'userEnteredValue': 'Not Required'},
                                {'userEnteredValue': 'Self-Sponsored / Freelance'}
                            ]
                        },
                        'showCustomUi': True,
                        'strict': False
                    }
                }
            }
        ]
        res = requests.post(f'https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}:batchUpdate', headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}, json={'requests': reqs})
        return {"status": res.status_code, "response": res.json()}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/setup-sheet2")
async def setup_sheet2():
    token = get_google_access_token()
    headers_row = [
        'Company',
        'Role Title',
        'Job Link / Source',
        'Rejection Category',
        'Visa Status',
        'Date Flagged',
        'Audit Flag Reason / Notes'
    ]
    url = f'https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values/Sheet2!A1:G1?valueInputOption=USER_ENTERED'
    res = requests.put(url, headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}, json={'values': [headers_row]})
    
    meta_url = f'https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}'
    meta_res = requests.get(meta_url, headers={'Authorization': f'Bearer {token}'})
    sheet2_id = None
    for s in meta_res.json().get('sheets', []):
        if s['properties']['title'] == 'Sheet2':
            sheet2_id = s['properties']['sheetId']
            break
            
    if sheet2_id is not None:
        format_body = {
            "requests": [
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet2_id,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": 7
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": {
                                    "red": 0.29,
                                    "green": 0.33,
                                    "blue": 0.41
                                },
                                "horizontalAlignment": "CENTER",
                                "textFormat": {
                                    "foregroundColor": {
                                        "red": 1.0,
                                        "green": 1.0,
                                        "blue": 1.0
                                    },
                                    "fontSize": 10,
                                    "bold": True
                                }
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
                    }
                },
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": sheet2_id,
                            "gridProperties": {
                                "frozenRowCount": 1
                            }
                        },
                        "fields": "gridProperties.frozenRowCount"
                    }
                },
                {
                    "autoResizeDimensions": {
                        "dimensions": {
                            "sheetId": sheet2_id,
                            "dimension": "COLUMNS",
                            "startIndex": 0,
                            "endIndex": 7
                        }
                    }
                }
            ]
        }
        batch_url = f'https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}:batchUpdate'
        requests.post(batch_url, headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}, json=format_body)
        
def fetch_existing_sheet_entries() -> set:
    """Returns a set of lowercased (company, role) and urls to prevent duplicate audits"""
    try:
        token = get_google_access_token()
        url = f'https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values/Sheet1!A2:C'
        res = requests.get(url, headers={'Authorization': f'Bearer {token}'}, timeout=10)
        if res.status_code == 200:
            rows = res.json().get('values', [])
            seen = set()
            for r in rows:
                if len(r) >= 2:
                    seen.add((r[0].strip().lower(), r[1].strip().lower()))
                if len(r) >= 3 and r[2].strip().startswith('http'):
                    seen.add(r[2].strip().lower())
            return seen
    except Exception as e:
        print("Error fetching existing sheet entries:", e)
    return set()

def process_apify_jobs_background(items: list, target_space: str) -> dict:
    existing_entries = fetch_existing_sheet_entries()
    print(f"Starting Apify ingestion for {len(items)} items. Target space: {target_space}")
    audited_count = 0
    skipped_count = 0
    
    for i, item in enumerate(items[:15]):
        if not item or not isinstance(item, dict):
            continue
            
        company = (
            item.get('companyName') or 
            item.get('company') or 
            item.get('employerName') or 
            item.get('company_name') or 
            'Unknown Company'
        ).strip()
        
        role = (
            item.get('title') or 
            item.get('jobTitle') or 
            item.get('positionName') or 
            item.get('role') or 
            'Open Position'
        ).strip()
        
        location = (
            item.get('location') or 
            item.get('formattedLocation') or 
            item.get('jobLocation') or 
            'Dubai, UAE'
        ).strip()
        
        # Extract apply URL from various scraper formats (Google Jobs, Indeed, LinkedIn, Bayt)
        apply_url = ''
        if item.get('apply_options') and isinstance(item['apply_options'], list) and len(item['apply_options']) > 0:
            apply_url = item['apply_options'][0].get('link') or item['apply_options'][0].get('url') or ''
        elif item.get('applyOptions') and isinstance(item['applyOptions'], list) and len(item['applyOptions']) > 0:
            apply_url = item['applyOptions'][0].get('link') or item['applyOptions'][0].get('url') or ''
            
        if not apply_url:
            apply_url = (
                item.get('jobUrl') or 
                item.get('applyUrl') or 
                item.get('applyLink') or
                item.get('url') or 
                item.get('link') or 
                item.get('job_link') or
                item.get('share_link') or
                item.get('shareLink') or
                item.get('google_jobs_url') or
                ''
            ).strip()
        
        description = (
            item.get('description') or 
            item.get('descriptionText') or 
            item.get('snippet') or 
            item.get('jobDescription') or 
            ''
        ).strip()
        
        # Deduplication check
        if (company.lower(), role.lower()) in existing_entries or (apply_url and apply_url.lower() in existing_entries):
            print(f"Skipping duplicate Apify job: {role} @ {company}")
            skipped_count += 1
            continue
            
        existing_entries.add((company.lower(), role.lower()))
        if apply_url:
            existing_entries.add(apply_url.lower())
            
        raw_job_lead = (
            f"Company: {company}\n"
            f"Role Title: {role}\n"
            f"Location: {location}\n"
            f"Apply Link: {apply_url}\n\n"
            f"Job Details & Requirements:\n"
            f"{description[:2500]}"
        )
        
        print(f"Auditing Apify job lead [{i+1}/{len(items)}]: {role} @ {company}...")
        try:
            data = call_gemini_audit(raw_job_text=raw_job_lead)
            
            company_res = str(data.get('company_name') or company)
            role_res = str(data.get('role_title') or role)
            career_url_res = str(data.get('career_url') or apply_url)
            visa = str(data.get('visa_sponsorship') or 'Not Specified')
            notes = str(data.get('audit_notes') or '')
            tech_stack = ', '.join(data.get('tech_stack_match') or [])
            is_scam = data.get('is_scam', False)

            import datetime
            now = datetime.datetime.now()
            date_added = now.strftime('%Y-%m-%d')
            follow_up_date = (now + datetime.timedelta(days=3)).strftime('%Y-%m-%d')

            if is_scam:
                reject_row = [company_res, role_res, career_url_res or 'N/A', 'Scam Flagged', visa, date_added, notes]
                append_to_sheet('Sheet2', reject_row)
                sheet_info = 'Logged to Sheet2 (Rejected Leads)'
            else:
                visa_status = 'Requires Sponsorship'
                apply_row = [company_res, role_res, career_url_res or 'N/A', '', visa_status, date_added, follow_up_date, tech_stack, notes]
                sheet_ok = append_to_sheet('Sheet1', apply_row)
                sheet_info = 'Logged to Sheet1 (Database)' if sheet_ok else 'Saved'

            card = build_card_obj(data, sheet_info, target_space)
            card_id = f'apify_{abs(hash(str(role_res) + str(company_res) + str(date_added)))}'

            post_res = post_chat_message(target_space, {
                'cardsV2': [{
                    'cardId': card_id,
                    'card': card
                }]
            })
            print(f"Delivered Apify card to Google Chat: {post_res.status_code}")
            audited_count += 1
        except Exception as err:
            print(f"Error auditing Apify lead {role} @ {company}:", err)

    return {"audited": audited_count, "skipped": skipped_count}

@app.post("/apify-webhook")
async def apify_webhook(request: Request, space: str = 'spaces/-acITKAAAAE', token: str = ''):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
        
    print("Received Apify Webhook POST:", json.dumps(payload)[:300])
    
    # Handle Apify test event
    if isinstance(payload, dict) and payload.get('eventType') == 'TEST':
        print("Apify test connection successful!")
        return {"status": "ok", "message": "Test ping successful!"}
        
    items = []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict) and 'items' in payload and isinstance(payload['items'], list):
        items = payload['items']
    elif isinstance(payload, dict):
        # Extract dataset ID from Apify standard webhook payload safely
        resource_obj = payload.get('resource') or {}
        event_obj = payload.get('eventData') or {}
        dataset_id = (
            resource_obj.get('defaultDatasetId') or
            event_obj.get('defaultDatasetId') or
            payload.get('defaultDatasetId')
        )
        apify_token = token or payload.get('token') or payload.get('apiToken') or os.environ.get('APIFY_API_TOKEN', '')
        
        if dataset_id:
            print(f"Fetching dataset items from Apify Dataset ID: {dataset_id}")
            try:
                apify_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?limit=25&clean=true"
                if apify_token:
                    apify_url += f"&token={apify_token}"
                res = requests.get(apify_url, timeout=20)
                if res.status_code == 200:
                    items = res.json()
                    print(f"Successfully fetched {len(items)} items from Apify dataset.")
                else:
                    print(f"Failed to fetch Apify dataset: HTTP {res.status_code} - {res.text[:150]}")
            except Exception as d_err:
                print("Error fetching Apify dataset items:", d_err)
                
    if not items:
        return {"status": "ok", "message": "No items found in dataset or webhook."}
        
    print(f"Synchronously processing {len(items)} scraped items for active Cloud Run CPU...")
    results = process_apify_jobs_background(items, space)
    
    return {
        "status": "success",
        "message": f"Processed {len(items)} items",
        "audited": results.get("audited", 0),
        "skipped": results.get("skipped", 0),
        "target_space": space
    }

@app.post("/")
async def chat_webhook(request: Request):
    try:
        event = await request.json()
    except Exception:
        event = {}

    print("Incoming Chat Webhook event:", json.dumps(event))

    # Handle Interactive Card Click Action (e.g. Clear Card)
    if event.get('type') == 'CARD_CLICKED' or event.get('action') or event.get('common', {}).get('invokedFunction'):
        action_data = event.get('action') or {}
        common_data = event.get('common') or {}
        
        params = {}
        # 1. From action.parameters list
        if isinstance(action_data.get('parameters'), list):
            for p in action_data['parameters']:
                if isinstance(p, dict) and 'key' in p:
                    params[p['key']] = p.get('value', '')
        # 2. From action.parameters dict
        elif isinstance(action_data.get('parameters'), dict):
            params.update(action_data['parameters'])
        # 3. From common.parameters dict
        if isinstance(common_data.get('parameters'), dict):
            params.update(common_data['parameters'])
            
        company = str(params.get('company') or 'Target Company')
        role = str(params.get('role') or 'Position')
        target_card_id = str(params.get('card_id') or event.get('cardId') or f'audit_{abs(hash(role + company))}')
        
        print(f"Clearing card {target_card_id} for {role} @ {company}")

        # Direct Google Chat REST API Patch
        msg_name = event.get('message', {}).get('name')
        if msg_name:
            try:
                token = get_google_access_token()
                patch_url = f"https://chat.googleapis.com/v1/{msg_name}?updateMask=cardsV2"
                headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
                cleared_payload = {
                    'cardsV2': [{
                        'cardId': target_card_id,
                        'card': {
                            'header': {
                                'title': f'{role} @ {company}',
                                'subtitle': '✅ Marked as Applied & Cleared'
                            },
                            'sections': [{
                                'widgets': [{
                                    'textParagraph': {
                                        'text': '<i>Application reviewed & cleared.</i>'
                                    }
                                }]
                            }]
                        }
                    }]
                }
                res = requests.patch(patch_url, json=cleared_payload, headers=headers, timeout=10)
                print(f"Direct REST API patch status for {msg_name}: {res.status_code} - {res.text[:200]}")
            except Exception as patch_err:
                print("Error directly patching message:", patch_err)

        return {
            'actionResponse': {
                'type': 'UPDATE_MESSAGE'
            },
            'cardsV2': [{
                'cardId': target_card_id,
                'card': {
                    'header': {
                        'title': f'{role} @ {company}',
                        'subtitle': '✅ Marked as Applied & Cleared'
                    },
                    'sections': [{
                        'widgets': [{
                            'textParagraph': {
                                'text': '<i>Application reviewed & cleared.</i>'
                            }
                        }]
                    }]
                }
            }]
        }

    space_name = (
        event.get('space', {}).get('name') or
        event.get('chat', {}).get('messagePayload', {}).get('space', {}).get('name') or
        event.get('message', {}).get('space', {}).get('name')
    )

    msg_obj = (
        event.get('message') or
        event.get('chat', {}).get('messagePayload', {}).get('message') or {}
    )
    raw_text = msg_obj.get('text', '').strip() or msg_obj.get('argumentText', '').strip()

    # Detect Image Attachments from Google Chat (Screenshots / Uploads)
    attachments = (
        msg_obj.get('attachment') or
        msg_obj.get('attachments') or
        []
    )
    if isinstance(attachments, dict):
        attachments = [attachments]

    image_bytes = None
    image_mime = 'image/png'

    if attachments and space_name:
        token = get_google_access_token()
        for att in attachments:
            content_type = att.get('contentType', '')
            res_name = (
                att.get('attachmentDataRef', {}).get('resourceName') or
                att.get('name') or
                ''
            )
            download_url = att.get('downloadUri')
            
            # Check if image format
            if 'image' in content_type or not content_type:
                target_url = download_url or (f"https://chat.googleapis.com/v1/media/{res_name}?alt=media" if res_name else None)
                if target_url:
                    try:
                        print(f"Downloading chat attachment from: {target_url} (res: {res_name})")
                        res = requests.get(target_url, headers={'Authorization': f'Bearer {token}'}, timeout=20)
                        if res.status_code == 200 and len(res.content) > 0:
                            image_bytes = res.content
                            image_mime = content_type or res.headers.get('Content-Type', 'image/png')
                            print(f"Successfully downloaded image ({len(image_bytes)} bytes, mime: {image_mime})")
                            break
                        else:
                            print(f"Failed to download image attachment: HTTP {res.status_code}")
                    except Exception as img_err:
                        print("Error downloading chat image:", img_err)

    if attachments and not image_bytes and not raw_text and space_name:
        post_chat_message(space_name, {
            'text': (
                "📸 *Screenshot Received!*\n\n"
                "Google Chat restricts direct file downloads for security. To audit this job lead in 2 seconds:\n"
                "👉 *Copy the text from your screenshot* (using iPhone Live Text, Google Lens, or Snipping Tool) and *paste it here*.\n\n"
                "I will immediately audit the role, log it to Sheet1, and build your tailored Gmail & WhatsApp outreach! 🚀"
            )
        })
        return {}

    if (raw_text or image_bytes) and space_name:
        try:
            print(f"Auditing job post (text len: {len(raw_text)}, has image: {image_bytes is not None})...")
            data = call_gemini_audit(raw_job_text=raw_text, image_bytes=image_bytes, mime_type=image_mime)

            company = str(data.get('company_name') or 'Target Company')
            role = str(data.get('role_title') or 'Open Position')
            career_url = str(data.get('career_url') or '')
            visa = str(data.get('visa_sponsorship') or 'Not Specified')
            notes = str(data.get('audit_notes') or '')
            tech_stack = ', '.join(data.get('tech_stack_match') or [])
            is_scam = data.get('is_scam', False)

            import datetime
            now = datetime.datetime.now()
            date_added = now.strftime('%Y-%m-%d')
            follow_up_date = (now + datetime.timedelta(days=3)).strftime('%Y-%m-%d')

            if is_scam:
                reject_row = [company, role, career_url or 'N/A', 'Scam Flagged', visa, date_added, notes]
                append_to_sheet('Sheet2', reject_row)
                sheet_info = 'Logged to Sheet2 (Rejected Leads)'
            else:
                visa_status = 'Requires Sponsorship'
                apply_row = [company, role, career_url or 'N/A', '', visa_status, date_added, follow_up_date, tech_stack, notes]
                sheet_ok = append_to_sheet('Sheet1', apply_row)
                sheet_info = 'Logged to Sheet1 (Database)' if sheet_ok else 'Saved'

            card = build_card_obj(data, sheet_info, space_name)
            card_id = f'audit_{abs(hash(str(role) + str(company) + str(date_added)))}'

            post_res = post_chat_message(space_name, {
                'cardsV2': [{
                    'cardId': card_id,
                    'card': card
                }]
            })
            print("Posted to chat space, response:", post_res.status_code, post_res.text)
        except Exception as audit_err:
            print('Audit error:', audit_err)
            post_chat_message(space_name, {'text': f'⚠️ Unable to audit job lead: {str(audit_err)}'})

    return {}