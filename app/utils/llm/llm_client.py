import logging
import textwrap
import time
from typing import List, Optional
import requests
import json
import os
from datetime import date



logger = logging.getLogger(__name__)

class LLMClient:
    
    def __init__(self, base_url=None, model="mistral", max_retries=3):
        self.base_url = base_url or os.getenv("LLM_BASE_URL", "http://host.docker.internal:11434") # For docker: http://ollama_llm:11434
        self.model = model
        self.max_retries = max_retries
    


    def analyze_grant(self, grant_text: str, mission: str, matched_keywords: list[str], feedback_examples: list[dict] | None = None,  org_context: list[dict] | None = None) -> dict:
        prompt = self._build_prompt(grant_text, mission, matched_keywords, feedback_examples, org_context)
        attempt = 0

        while attempt < self.max_retries:
            try:
                response = requests.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False
                    },
                    timeout=300
                )
                response.raise_for_status()

               
                raw = response.json()
                try:
                    return json.loads(raw["response"])
                except (json.JSONDecodeError, KeyError) as parse_err:
                    raise ValueError(f"Invalid or malformed JSON from LLM:\n{raw.get('response', '')}") from parse_err

            except (requests.RequestException, ValueError) as e:
                attempt += 1
                if attempt >= self.max_retries:
                    logger.error(f" Failed to get valid response from LLM after {self.max_retries} attempts.")  
                    raise RuntimeError(f"LLM request failed: {e}")
                wait_time = 2 ** attempt
                logger.warning(f"Retry {attempt}/{self.max_retries} after error: {e}. Waiting {wait_time}s...")  
                time.sleep(wait_time)


    def _build_prompt(self, grant_text: str, mission: str, matched_keywords: List[str], feedback_examples: Optional[List[dict]] = None, org_context: Optional[List[dict]] = None) -> str:
        today = date.today().isoformat()
        kw_line = f"Matched keywords: {', '.join(matched_keywords)}" if matched_keywords else "Matched keywords: (none)"
        
        examples_section = ""
        if feedback_examples:
            lines = []
            for ex in feedback_examples[:3]:
                fl = ex.get("final_labels", {})
                lbl = ", ".join([f"{k}={fl.get(k)!r}" for k in ("is_relevant","location_applicable","award_amount","deadline") if k in fl])
                rationale = ex.get("rationale") or ""
                lines.append(f"- Example: {ex.get('url','')}\n  Labels: {lbl}\n  Rationale: {rationale}\n  Snippet: {ex.get('snippet','')[:300]}")
            if lines:
                examples_section = "Retrieved Feedback Examples:\n" + "\n".join(lines)
        
        org_section = ""
        if org_context:
            kb_lines = []
            for row in org_context[:3]:  
                kb_lines.append(f"- [{row.get('doc','')}] (p{row.get('priority',0)}): {row.get('snippet','')[:240]}")
            if kb_lines:
                org_section = "Org Policy Context:\n" + "\n".join(kb_lines)


        prompt = textwrap.dedent(f"""
                    You are analyzing a grant opportunity for two organizations. Use the following organizational contexts:
                    This detail is important to determine if the grant is relevant for either of the organizations and to extract the funding amount.

                    Mission:
                        \"\"\"
                        {mission.strip()}
                        \"\"\"
                    {kw_line}
                    {org_section if org_section else ""}
                    {examples_section if examples_section else ""}

                    Today's date: {today}

                    Grant Text:
                        \"\"\"
                        {grant_text}
                        \"\"\"

                    Your tasks:
                     1. Determine if the grant is relevant for the organization.

                    Important exclusions:
                    - If the opportunity is a residency (e.g., artist residency), set is_relevant to false and explain that it is a residency.
                    - If the opportunity is a course, class, or workshop, set is_relevant to false and explain that it is a course.
                    - If the opportunity is related to emergency assistance or relief (e.g., emergency grants), set is_relevant to false and explain that it is emergency-related.
                    - If the grant is age-restricted to under 35 (example 18–24 age group), set is_relevant to false and explain the age restriction. Age limits above 35 are acceptable.
                    - Visual arts are not relevant unless explicitly include filmmaking/video and photography grants are never relevant.

                    If the grant is not relevant, do not attempt to extract award_amount, deadline, or priority_score. Just set is_relevant to false and include the reason in the explanation field.


                    2.  Extract every amount of funding from the Grant Text. The amount may appear in any of these formats:
                        With a dollar sign (e.g., $1,000, $1000, $10,000)

                        With the word "dollars" or "USD" after the number (e.g., 1000 dollars, 1200 USD)

                        As a plain number clearly describing a funding limit or amount (e.g., up to 1000, maximum 2500)

                        As written out words describing an amount (e.g., "five hundred dollars", "ten thousand USD")

                    3. Evaluate and return a JSON with the following fields:
                    - is_relevant: true or false
                    - location_applicable: true or false
                    - award_amount: string or null
                    - deadline: string or null
                    - explanation: short justification

                    4. Additionally, return:
                    - priority_score: integer from 0 to 100 based on:
                        - Deadline proximity (closer is higher priority)
                        - Larger funding amounts increase priority
                        - More number of awards increases priority
                        - Relevance based on:
                            - General relevance (adds points)
                            - If it targets music or visual arts with filmmaking: +points
                            - If it targets Texas: +points
                            - If it targets Houston: +more points
                            - If it in any way targets South-East Asian or Indian artists/art forms or music: +more points

                    - possibility: one of ["Poor", "Decent", "Fair", "Excellent"] based on:
                        - Relevance to mission
                        - Number of awards
                        - Specific targeting (see above list)
                        - If there is only one award and it targets unrelated demographics/geography, mark as "Poor"
                        - More awards + highly targeted grants = "Excellent"
                        - If it is generic such as "general operating support" or "general music grants", mark as "Decent" or "Fair" based on funding amount and deadline proximity

                    Only respond with valid JSON like this:
                    {{
                    "is_relevant": true,
                    "location_applicable": true,
                    "award_amount": "$5000",
                    "deadline": "2025-09-15",
                    "explanation": "The grant is not relevant as it focuses on Photography, which does not align with Riyaaz Qawwali's mission. ",
                    "priority_score": 87,
                    "possibility": "Fair"
                    }}

                    Respond only with valid JSON and make sure to return all JSON values cleanly. Do not double-quote or single-quote inside string values. Do not hallucinate or fabricate information. Make sure the JSON is valid and contains all required fields.
                    Also make sure you make very sincere attempt to extract the funding amount, deadline, and relevance of the grant based on the provided context. Leave fields null if data is unavailable. 
                    Be especially careful to avoid misinterpreting residencies or courses as grants. Photography grants are not relevant. Visual arts grants are not relevant unless they specifically mention filmmaking or video production. Film making grants are relevant and even more relevant if targeted towards artists or musicians or Asians/Southeast Asians.
                    """.strip())
        return prompt
