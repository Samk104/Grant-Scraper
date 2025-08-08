import logging
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit  
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from app.scrapers.base_scraper import BaseScraper
from app.utils.extractors import extract_emails, extract_amount

logger = logging.getLogger(__name__)

class GenericScraper(BaseScraper):
    def scrape(self, driver):
        if driver is None:
            logger.error("GenericScraper: Could not obtain a webdriver instance.")
            return []

        all_opportunities = []
        url = self.config.get("url")
        seen_urls = set()

        driver.get(url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        logger.info("GenericScraper: Page loaded successfully.")

        
        match_terms = self.config.get("match_terms", [
            "grant", "funding", "fellowship", "opportunity", "award", "support", "scholarship", "program"
        ])

        
        xpath_conditions = " or ".join([
            f"contains(translate(string(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{term.lower()}')"
            for term in match_terms
        ])

        candidates = driver.find_elements(
            By.XPATH,
            f"//a[{xpath_conditions}]"
        )
        logger.info(f"GenericScraper: Found {len(candidates)} candidate links matching keywords.")

        
        parent = driver.current_window_handle

        for link in candidates:
            try:
                
                raw_href = link.get_attribute("href")
                if not raw_href:
                    continue
                href = self._normalize_url(url, raw_href)  
                if href in seen_urls:
                    continue
                seen_urls.add(href)

                
                title = (link.text.strip() or link.get_attribute("title") or "Untitled").strip()

                
                driver.execute_script("window.open(arguments[0]);", href)
                driver.switch_to.window(driver.window_handles[-1])
                WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

                
                try:
                    page_text = driver.find_element(By.TAG_NAME, "body").text
                except Exception:
                    logger.warning("GenericScraper: Failed to get page text.")
                    page_text = ""

                
                if len(page_text) < 300:
                    logger.info("GenericScraper: Skipping page due to insufficient content.")
                    continue

                
                paragraphs = [p.strip() for p in page_text.split("\n") if len(p.strip()) > 40]
                description = "\n".join(paragraphs[:5]) if paragraphs else "No useful text found"

                emails = extract_emails(page_text)
                amounts = extract_amount(page_text)
                deadline = self.extract_deadline_guess(page_text)

                all_opportunities.append({
                    "title": title,
                    "url": href,
                    "description": description,
                    "grant_amount": ", ".join(amounts) if amounts else "",
                    "email": ", ".join(emails) if emails else "",
                    "deadline": deadline if deadline else "",
                    "tags": "Generic"
                })

            except Exception as e:
                logger.warning(f"GenericScraper: Failed to process candidate: {e}")
            finally:
                
                try:
                    if driver.current_window_handle != parent:
                        driver.close()
                except Exception:
                    
                    pass
                try:
                    driver.switch_to.window(parent)
                except Exception:
                    
                    pass

        logger.info(f"GenericScraper: Scraped {len(all_opportunities)} opportunities.")
        return all_opportunities

    def _normalize_url(self, base: str, href: str) -> str:
        abs_url = urljoin(base, href or "")
        parts = urlsplit(abs_url)
        path = parts.path.rstrip("/") or "/"   
        
        return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))

    def extract_deadline_guess(self, text: str) -> str:
        
        date_pattern = (
            r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
            r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
            r"\s+(?:[1-9]|[12][0-9]|3[01])(?:st|nd|rd|th)?,?\s+\d{4}\b"
        )

        matches = re.findall(date_pattern, text, re.IGNORECASE)
        for match in matches:
            
            normalized = re.sub(r"(st|nd|rd|th)", "", match, flags=re.IGNORECASE).strip()
            
            for fmt in ("%B %d, %Y", "%b %d, %Y"):
                try:
                    d = datetime.strptime(normalized, fmt)
                    if d.date() >= datetime.now(timezone.utc).date():
                        return d.strftime("%Y-%m-%d")
                    break  
                except ValueError:
                    continue
        return ""
