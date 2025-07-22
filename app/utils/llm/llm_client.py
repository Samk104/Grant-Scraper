import logging
import time
import requests
import json
import os


logger = logging.getLogger(__name__)

class LLMClient:
    
    def __init__(self, base_url=None, model="mistral", max_retries=3):
        self.base_url = base_url or os.getenv("LLM_BASE_URL", "http://ollama_llm:11434")
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
        return f"""
                    You are analyzing a grant opportunity. Use the following organizational context:
                    This detail is important to determine if the grant is relevant for the organization and to extract the funding amount.
                    Mission: {context.get('mission')}
                    Keywords: {', '.join(context.get('keywords', []))}
                    Feedback: {context.get('feedback', 'None')}

                    Grant Text:
                    \"\"\"
                    {grant_text}
                    \"\"\"
                    Extract every amount of funding from the following text. The amount may appear in any of these formats:
                        With a dollar sign (e.g., $1,000, $1000, $10,000)

                        With the word "dollars" or "USD" after the number (e.g., 1000 dollars, 1200 USD)

                        As a plain number clearly describing a funding limit or amount (e.g., up to 1000, maximum 2500)

                        As written out words describing an amount (e.g., "five hundred dollars", "ten thousand USD")
                    Return a JSON with:
                    - is_relevant: true/false
                    - location_applicable: true/false
                    - award_amount: string or null
                    - deadline: string or null
                    - explanation: short justification

                    Respond only with valid JSON and make sure to return all JSON values cleanly. Do not double-quote or single-quote inside string values. Please do not hallucinate or make up information or unwarranted assumptions. Make sure the JSON is valid and contains all required fields.
                    Also make sure you make very sincere attempt to extract the funding amount, deadline, and relevance of the grant based on the provided context. We are only interested in
                    grants and not residencies, please keep that in mind. If you encounter a residency, please return is_relevant as false and explain that it is a residency in the explanation field.
                    """.strip()
