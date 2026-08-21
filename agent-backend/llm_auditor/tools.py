# Imports type annotations for lists and optional (nullable) fields
from typing import List, Optional
# Imports Pydantic to enforce exact data structure validation
from pydantic import BaseModel, Field


# Defines the schema that the Reviser Sub-Agent must strictly return
class JobAuditOutput(BaseModel):
    # Company name as a string
    company_name: str = Field(description="Name of the hiring company")
    
    # Job title as a string
    role_title: str = Field(description="Title of the job position")
    
    # A numerical confidence rating from 0.0 to 1.0 indicating if the job posting is real
    legitimacy_score: float = Field(
        description="Confidence score between 0.0 and 1.0 indicating if the job posting is real"
    )
    
    # Boolean flag marking whether suspicious scam patterns were detected
    is_scam: bool = Field(
        description="True if posting contains scam indicators, false otherwise"
    )
    
    # Clean standardized string for visa status: 'Available', 'Not Available', or 'Not Specified'
    visa_sponsorship: str = Field(
        description="Visa sponsorship status: 'Available', 'Not Available', or 'Not Specified'"
    )
    
    # List containing matching technical requirements (e.g., ['Python', 'SQL'])
    tech_stack_match: List[str] = Field(
        default_factory=list,
        description="List of primary technical skills and tools extracted"
    )
    
    # Official link if verified online; defaults to None if not found
    career_url: Optional[str] = Field(
        default=None,
        description="Verified career portal or official job URL found during search"
    )
    
    # Detailed justification and cross-checks from the auditing agent
    audit_notes: str = Field(
        description="Summary of reasoning, cross-checks, and findings"
    )

    # Detected recruiter / HR contact email (if present in the posting)
    contact_email: Optional[str] = Field(
        default=None,
        description="Direct recruiter or HR contact email detected in the job posting text (null if none)"
    )

    # Detected recruiter / HR phone, mobile, or WhatsApp number (if present)
    contact_phone: Optional[str] = Field(
        default=None,
        description="Direct recruiter phone, mobile, or WhatsApp number detected in the posting (null if none)"
    )

    # Tailored email subject line for Thabeeb Jafran applying to this role
    tailored_email_subject: Optional[str] = Field(
        default=None,
        description="High-converting email subject line for Thabeeb Jafran applying to this role"
    )

    # Tailored cover email body customized to the job requirements using Thabeeb's profile
    tailored_email_body: Optional[str] = Field(
        default=None,
        description="Tailored, high-impact cover email body matching Thabeeb's profile, projects, and portfolio to the job requirements"
    )

    # Tailored WhatsApp message formatted for mobile recruiter outreach
    tailored_whatsapp_message: Optional[str] = Field(
        default=None,
        description="Concise, punchy WhatsApp message formatted for mobile recruiter outreach with portfolio link"
    )