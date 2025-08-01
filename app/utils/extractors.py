import re
import spacy
from word2number import w2n
from typing import List


nlp = spacy.load("en_core_web_sm")

def extract_amount(text: str, hint: str =None):
        def normalize_text(txt):
            return txt.replace("–", "-").replace("—", "-")

        def convert(value, unit):
            value = value.replace(",", "")
            multiplier = {"k": 1_000, "m": 1_000_000}
            return int(float(value) * multiplier.get(unit.lower(), 1))

        amounts = []

        text = normalize_text(text)
        hint = normalize_text(hint or "")
        combined_text = f"{hint} {text}"

        single_amount_pattern = re.compile(
            r"(?:(?:[\$€£])\s?|(?:USD|usd|dollars|eur|euro|gbp|pounds)\s?)"
            r"(\d{1,3}(?:[,.\s]?\d{3})*(?:[.,]?\d+)?)([KkMm]?)"
        )

        for match in single_amount_pattern.finditer(combined_text):
            num, unit = match.groups()
            try:
                amount = convert(num, unit)
                amounts.append(f"${amount}")
            except:
                continue

        range_pattern = re.compile(
            r"(?:(?:[\$€£]|USD|usd|dollars)\s?)?(\d+(?:[,.\d]*)?)([KkMm]?)\s?(?:to|–|-|and)\s?(?:[\$€£]|USD|usd|dollars)?\s?(\d+(?:[,.\d]*)?)([KkMm]?)"
        )

        for match in range_pattern.finditer(combined_text):
            num1, unit1, num2, unit2 = match.groups()
            try:
                amount1 = convert(num1, unit1)
                amount2 = convert(num2, unit2)
                amounts.append(f"${amount1}-${amount2}")
            except:
                continue

        doc = nlp(combined_text.lower())
        for sent in doc.sents:
            if any(keyword in sent.text for keyword in ["dollar", "usd", "$"]):
                try:
                    words = sent.text.replace("-", " ").split()
                    for i in range(len(words)):
                        phrase = " ".join(words[i:i+5])
                        value = w2n.word_to_num(phrase)
                        amounts.append(f"${value}")
                except:
                    continue

        return list(set(amounts)) or ["Not Available"]
    
    
    

def extract_emails(text: str) -> List[str]:
    if not text:
        return []

    obfuscations = [
        (r"\s*\[at\]\s*", "@"),
        (r"\s*\(at\)\s*", "@"),
        (r"\s+at\s+", "@"),
        (r"\s*\[dot\]\s*", "."),
        (r"\s*\(dot\)\s*", "."),
        (r"\s+dot\s+", "."),
    ]

    clean_text = text.lower()

    for pattern, replacement in obfuscations:
        clean_text = re.sub(pattern, replacement, clean_text, flags=re.IGNORECASE)

    email_regex = re.compile(
        r"[\w\.-]+@[\w\.-]+\.\w{2,}",
        flags=re.IGNORECASE
    )

    found = email_regex.findall(clean_text)

    return list(set(email.strip().lower() for email in found))


