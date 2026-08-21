import os
import sys
import json
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field

# Locate root directory and load credentials
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

creds_path = str(ROOT_DIR.parent / "credentials.json")
if os.path.exists(creds_path):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path

import vertexai
from vertexai.preview import reasoning_engines

PROJECT_ID = "job-auditor-1787020056"
REGION = "us-central1"
BUCKET = "gs://job-auditor-bucket-job-auditor-1787020056-aonmzc"


# Output schema definition
class JobAuditOutput(BaseModel):
    company_name: str = Field(description="Name of the hiring company")
    role_title: str = Field(description="Title of the job position")
    legitimacy_score: float = Field(description="Confidence score between 0.0 and 1.0")
    is_scam: bool = Field(description="Scam or fraud flag")
    visa_sponsorship: str = Field(description="Visa status: Available | Not Specified | No")
    tech_stack_match: List[str] = Field(default_factory=list, description="Matched skills")
    career_url: Optional[str] = Field(default=None, description="Official career link")
    audit_notes: str = Field(description="Critic verification notes")
    contact_email: Optional[str] = Field(default=None, description="HR / Recruiter email found in posting (or null)")
    contact_phone: Optional[str] = Field(default=None, description="HR / Recruiter phone or WhatsApp found in posting (or null)")
    tailored_email_subject: Optional[str] = Field(default=None, description="Tailored email subject line for Thabeeb Jafran")
    tailored_email_body: Optional[str] = Field(default=None, description="High-converting tailored cover email for Thabeeb Jafran matching job requirements")
    tailored_whatsapp_message: Optional[str] = Field(default=None, description="Concise, punchy WhatsApp message formatted for mobile recruiter outreach")


with open('profile/Thabeeb_Jafran_Master_Technical_Portfolio.pdf', 'rb') as f:
    PORTFOLIO_PDF_BYTES = f.read()

with open('profile/ThabeebJafranResume.pdf', 'rb') as f:
    RESUME_PDF_BYTES = f.read()


# Fully self-contained Reasoning Engine class
class JobAuditorReasoningEngine:
    """Vertex AI Native Reasoning Engine for Multi-Modal Job Auditing & Tailored Outreach."""

    def __init__(self, project_id: str = "job-auditor-1787020056", location: str = "us-central1", model_name: str = "gemini-2.5-flash"):
        self.project_id = project_id
        self.location = location
        self.model_name = model_name
        self.portfolio_bytes = PORTFOLIO_PDF_BYTES
        self.resume_bytes = RESUME_PDF_BYTES

    def set_up(self):
        """Executed upon remote container startup."""
        from google import genai
        self._client = genai.Client(vertexai=True, project=self.project_id, location=self.location)

    def query(self, raw_job_text: str) -> str:
        """Executes multi-agent audit, contact extraction, and multi-modal tailored outreach synthesis."""
        from google.genai import types

        if not hasattr(self, "_client") or self._client is None:
            self.set_up()

        # Step 1: Concise Critic verification with Google Search Grounding
        critic_prompt = f"""
        Quickly verify company legitimacy, official career URL, any recruiter email/phone contacts, and scam indicators in 2-3 short bullet points:
        {raw_job_text}
        """
        critic_res = self._client.models.generate_content(
            model=self.model_name,
            contents=critic_prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                max_output_tokens=1024
            )
        )
        critic_text = critic_res.text if (critic_res and critic_res.text) else "No web results found."

        # Step 2: Multi-Modal synthesis reading raw PDF documents directly with strict response_schema
        schema_json = json.dumps(JobAuditOutput.model_json_schema())
        reviser_prompt = f"""
        You are a technical career assistant for Thabeeb Jafran, a Data Analyst, Business Analyst, and MIS graduate based in Dubai.

        Use the attached Technical Portfolio PDF and Resume PDF, together with the Job Description below, to tailor the application.

        Critic Verification Notes:
        {critic_text}

        Return ONLY one valid JSON object with these exact keys:
        company_name, role_title, contact_email, contact_phone, career_url, legitimacy_score, is_scam, visa_sponsorship, tech_stack_match, audit_notes, tailored_angle, tailored_email_subject, tailored_email_body, tailored_whatsapp_message

        Rules:
        - notes must be a one-sentence role summary.
        - tailored_angle must identify the strongest matching portfolio or resume experience.
        - email_body must be professional, tailored, under 150 words, and have no sign-off.
        - whatsapp_message must be professional, tailored, copyable, and under 100 words.
        - Extract a recruiter email into contact_email when present.
        - Extract a WhatsApp or mobile number into contact_phone when present.

        Job Description:
        {raw_job_text}

        Schema:
        {schema_json}
        """
        contents = [
            types.Part.from_bytes(data=self.portfolio_bytes, mime_type="application/pdf"),
            types.Part.from_bytes(data=self.resume_bytes, mime_type="application/pdf"),
            types.Part.from_text(text=reviser_prompt)
        ]
        reviser_res = self._client.models.generate_content(
            model=self.model_name,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=JobAuditOutput,
                max_output_tokens=8192
            )
        )
        return reviser_res.text


# Initialize Vertex AI
vertexai.init(project=PROJECT_ID, location=REGION, staging_bucket=BUCKET)

print("Deploying Multi-Modal Reasoning Engine to Vertex AI...")
remote_engine = reasoning_engines.ReasoningEngine.create(
    JobAuditorReasoningEngine(project_id=PROJECT_ID, location=REGION, model_name="gemini-2.5-flash"),
    requirements=[
        "google-genai>=0.1.1",
        "google-cloud-aiplatform[reasoningengine,agent_engines]>=1.60.0",
        "pydantic>=2.0.0",
        "cloudpickle>=3.0.0"
    ],
    display_name="Job Ingestion & Auditing Agent"
)

print("\nDeployment Complete! Resource Name:")
print(remote_engine.resource_name)
