from typing import Optional

TEMPLATES = {

  "document_extraction": {
    "v1": """Extract structured data from this insurance
submission document.

Document Type: {document_type}
Document Content:
{document_content}

Extract ALL relevant fields. Return ONLY valid JSON with
no extra explanation text:
{{
  "document_type": "{document_type}",
  "submission_id": "value from document",
  "extracted_fields": {{
    "field_name": "value"
  }},
  "confidence": 0.95,
  "notes": "any issues found during extraction"
}}

Fields to extract per document_type:

application:
  insured_name, business_type, industry_sic,
  annual_revenue, employee_count, effective_date,
  requested_coverage, requested_limits,
  years_in_business, prior_carrier

fleet_schedule:
  vehicle_count, vehicle_types, model_years,
  total_fleet_value, garaging_locations,
  radius_of_operation, states_operated,
  driver_list_provided

loss_history:
  total_claims, total_incurred, largest_loss,
  loss_ratio, policy_period, claim_types

property_schedule:
  property_count, building_addresses,
  construction_types, square_footage,
  building_values, occupancy_types,
  protection_class, sprinkler_present

building_details:
  roof_type, roof_year, electrical_updated,
  alarm_system, fire_suppression, stories

revenue_info:
  annual_revenue, revenue_by_segment,
  revenue_trend, largest_client_percentage

operations_description:
  primary_operations, locations, hazards,
  safety_programs, prior_claims,
  contractors_used, subcontractors

Return ONLY the JSON object. No markdown. No explanation."""
  },

  "lob_classification": {
    "v1": """Classify this insurance submission into the
correct line of business.

Extracted documents data:
{parsed_data_json}

EXAMPLE 1:
Documents present: fleet_schedule, loss_history, application
  with requested_coverage commercial_auto
Classification: commercial_auto
Reasoning: Fleet schedule with vehicles present.
  Driver list referenced. Auto loss history provided.
  Application requests commercial auto coverage.

EXAMPLE 2:
Documents present: property_schedule, building_details,
  application with requested_coverage commercial_property
Classification: commercial_property
Reasoning: Property schedule with buildings present.
  Building construction details provided.
  Application requests property coverage.

EXAMPLE 3:
Documents present: revenue_info, operations_description,
  application with requested_coverage general_liability
Classification: general_liability
Reasoning: Operations description present.
  Revenue information provided.
  No vehicles or buildings in submission.
  Application requests GL coverage.

EXAMPLE 4:
Documents present: fleet_schedule, property_schedule,
  application with requested_coverage commercial_auto
  AND commercial_property
Classification: multi_line
Reasoning: Both fleet schedule and property schedule
  present. Application explicitly requests two lines
  of coverage. This is a multi-line submission.

Now classify the given submission step by step:
Step 1: List all document types present in submission
Step 2: Identify which line each document belongs to
Step 3: Check requested_coverage field in application
Step 4: Determine if single line or multi-line
Step 5: State final classification with confidence

Return ONLY valid JSON:
{{
  "primary_line": "commercial_auto OR
                   commercial_property OR
                   general_liability OR
                   multi_line",
  "secondary_lines": [],
  "confidence": 0.97,
  "reasoning": "full step by step reasoning here"
}}"""
  },

  "completeness_validation": {
    "v1": """Validate completeness of this {line_of_business}
submission.

Extracted data from all documents:
{parsed_data_json}

Required fields for {line_of_business}:
{required_fields_json}

Think through this step by step:
Step 1: List every required field for {line_of_business}
Step 2: For each required field check if it was extracted
Step 3: Mark each field as complete, partial, or missing
Step 4: Count how many fields are complete vs missing
Step 5: Calculate score = complete_count divided by
        total_required_count
Step 6: List all missing field names clearly

Return ONLY valid JSON:
{{
  "completeness_score": 0.92,
  "field_status": {{
    "field_name": {{
      "status": "complete OR partial OR missing",
      "value": "extracted value or null if missing",
      "note": "explanation if partial or missing"
    }}
  }},
  "missing_fields": ["field1", "field2"],
  "validation_notes": "overall assessment of submission"
}}"""
  },

  "routing_decision": {
    "v1": """Determine the correct underwriting queue for
this insurance submission.

Line of business  : {line_of_business}
Completeness score: {completeness_score}
Missing fields    : {missing_fields_json}

Apply these routing rules in exact order:
Rule 1: If completeness_score is less than 0.7
        then route to Hold Queue regardless of line
Rule 2: If line is commercial_auto
        then route to Auto Queue
Rule 3: If line is commercial_property
        then route to Property Queue
Rule 4: If line is general_liability
        then route to GL Queue
Rule 5: If line is multi_line
        then route to Mixed Queue

Priority rules:
- Mark as urgent if effective_date is within 30 days
- Mark as urgent if total premium likely over 500000
- All others are routine

Return ONLY valid JSON:
{{
  "queue": "Auto Queue OR Property Queue OR
            GL Queue OR Mixed Queue OR Hold Queue",
  "routing_reason": "explanation of why this queue",
  "priority": "routine OR urgent",
  "action_needed": "none OR request_missing_info
                    OR manual_review"
}}"""
  },

  "user_profiling": {
    "v1": """Determine this user role from their message
and conversation history.

User message        : {user_message}
Conversation history: {conversation_history}

Clerk indicators to look for:
- Asks what fields are required
- Processes one submission at a time
- Uses phrases like I am new or help me understand
- Needs step by step explanations
- Asks what to do next after processing
- Unfamiliar with insurance terminology

Manager indicators to look for:
- Submits multiple submissions as a batch
- Asks about stats, counts, accuracy rates
- Uses technical insurance terms confidently
- Wants summary tables not detailed breakdowns
- Asks about routing distribution or throughput
- Mentions managing a team or reviewing results

Return ONLY valid JSON:
{{
  "role": "clerk OR manager",
  "confidence": 0.85,
  "signals": [
    "list of specific indicators observed"
  ]
}}"""
  },

  "intake_summary": {
    "v1": """Generate an intake summary report for
submission {submission_id}.

Parsed documents data : {parsed_data_json}
Validation result     : {validation_result_json}
Routing decision      : {routing_json}
User role             : {user_role}

STRICT RULES - NEVER violate these:
- Output plain readable text ONLY. No JSON. No markdown code fences.
- Do NOT write "I am a clerk", "I am a manager", or ANY sentence mentioning the user role.
- Do NOT introduce yourself or state your role in any way.
- The user_role field is ONLY used to pick verbose vs concise below.
- Begin your response DIRECTLY with the first header line (submission id and insured name).

If user_role is clerk, use this EXACT section order and titles (fill from parsed/validation/routing data; omit a subsection only if there is truly no data for it):

First line: the submission id and insured legal name separated by a hyphen and space, e.g. SUB-001 - Pacific Freight Lines Inc. (use real values from the parsed application).

Insured Information:

* Insured Name: ...
* Business Type: ...
* Industry SIC Code: ...
* Annual Revenue: ... (use US currency style e.g. $45,000,000)
* Employee Count: ...
* Years in Business: ... (if present in parsed data; otherwise say "Not stated")
* Prior Carrier: ...

Coverage Details:

* Effective Date: ... (spell month name, e.g. July 1, 2026)
* Requested Coverage: ... (human readable, e.g. Commercial Auto)
* Requested Limits:
  * Combined Single Limit: ...
  * Aggregate Limit: ...

Fleet Information:

* Vehicle Count: ... (e.g. 85 vehicles)
* Vehicle Types: ... (if present; else infer briefly from fleet_schedule or say "Not stated")
* Model Years: ... (comma-separated)
* Total Fleet Value: ... (US currency)
* Garaging Locations: ... (dedupe ZIPs, comma-separated)
* Radius of Operation: ... (e.g. 500 miles)
* States Operated In: ... (spell state names with abbreviations in parentheses)

Loss History (Policy Period ...):

* Total Claims: ...
* Total Incurred Loss: ...
* Largest Loss: ...
* Loss Ratio: ...
* Claim Types: ... (comma-separated Title Case)

Missing Information:

* If anything is missing or partial per validation, start lines with the warning emoji then plain English.
* What to ask for: Explain what to request from the broker (e.g. complete driver list with license numbers) when driver_list or similar is incomplete.

Classification: ...

Completeness Score: ... (e.g. "8 out of 10 fields are complete" — derive from validation field_status and required fields)

Queue Assignment:

* Queue: ...
* Next Steps: ...
* Reasoning: ... (one short sentence from routing_reason and action_needed)

If user_role is manager, use the EXACT SAME section order, titles, and bullet points as the clerk above. However, keep the descriptions slightly more brief and concise where possible (for example, in the Missing Information or Reasoning sections). 
- Do NOT remove any of the main sections. 
- Ensure it is highly readable and structured.
- No JSON. No code blocks.

Use human-readable labels (Title Case section titles). Format currency and large numbers clearly."""
  }

}


class PromptManager:
    def __init__(self):
        self._templates = TEMPLATES
        self._usage_log = []

    def get_prompt(
        self,
        template_name: str,
        version: str = "v1",
        variables: Optional[dict] = None
    ) -> str:
        if template_name not in self._templates:
            raise ValueError(
                f"Template not found: {template_name}"
            )
        if version not in self._templates[template_name]:
            raise ValueError(
                f"Version not found: {version}"
            )
        template = self._templates[template_name][version]
        rendered = template.format_map(variables or {})
        self._usage_log.append({
            "template": template_name,
            "version": version,
            "variables_keys": list((variables or {}).keys())
        })
        return rendered

    def list_templates(self) -> list:
        return list(self._templates.keys())

    def get_versions(self, template_name: str) -> list:
        return list(self._templates[template_name].keys())

    def get_usage_log(self) -> list:
        return self._usage_log
