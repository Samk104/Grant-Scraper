import logging
import time
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
    


    def analyze_grant(self, text: str, context: dict) -> dict:
        prompt = self._build_prompt(text, context)
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


    def _build_prompt(self, grant_text: str, context: dict) -> str:
        today = date.today().isoformat()

        return f"""
                    You are analyzing a grant opportunity. Use the following organizational context:
                    This detail is important to determine if the grant is relevant for the organization and to extract the funding amount.

                    Mission: {context.get('mission')}
                    Keywords: {', '.join(context.get('keywords', []))}
                    Feedback: {context.get('feedback', 'None')}

                    Today's date: {today}

                    Grant Text:
                    \"\"\"
                    {grant_text}
                    \"\"\"

                    Your tasks:
                    1. Determine if the grant is relevant for the organization. Important: If the opportunity is a residency (artist residency, etc.), do not attempt to extract award_amount, deadline, priority_score, or possibility, just mark is_relevant to false and explain that it is a residency in the explanation field.
                    Also the grant is not relevant, do noy attempt to extract funding amount, deadline, or priority score. Just set is_relevant to false and explain why it is not relevant in the explanation field. Also most of the time, any emergency related grants are not relevant, so set is_relevant to false and explain why it is not relevant in the explanation field.


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
                    Be especially careful to avoid misinterpreting residencies as grants. If it is a residency, set is_relevant to false and explain. Photography grants are not relevant. Visual arts grants are not relevant unless they specifically mention filmmaking or video production. Film making grants are relevant and even more relevant if targeted towards artists or musicians.
                    """.strip()
