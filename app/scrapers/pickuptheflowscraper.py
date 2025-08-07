import logging
import time
import re
from datetime import datetime, timezone
from dateutil import parser
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from app.scrapers.base_scraper import BaseScraper
from app.utils.driver_pool import get_driver_pool
from app.utils.text_from_image import extract_text_from_image_advanced
from app.utils.extractors import extract_amount, extract_emails
import spacy


nlp = spacy.load("en_core_web_sm")

logger = logging.getLogger(__name__)

class PickupTheFlowScraper(BaseScraper):
    def scrape(self):
        driver = get_driver_pool().get_driver()
        if driver is None:
            logger.error("PickupTheFlow: Could not obtain a webdriver instance.")
            return []

        all_opportunities = []
        config = self.config

        try:
            driver.get(config["url"])
            logger.info("PickupTheFlow: Loaded initial page.")
            curr_year = datetime.now(timezone.utc).year

            seen_links = set()

            while True:
                time.sleep(2)
                self.gradual_scroll(driver)
                articles = driver.find_elements(By.CSS_SELECTOR, config["article_selector"])

                logger.info(f"PickupTheFlow: Found {len(articles)} articles")

                keep_going = True
               
                for article in articles:
                    try:
                        date_elem = article.find_element(By.CSS_SELECTOR, config["date_selector"])
                        date_str = date_elem.get_attribute("datetime")
                        article_year = parser.parse(date_str).year

                        if article_year < curr_year:
                            logger.info("PickupTheFlow: Reached articles from a previous year. Stopping.")
                            keep_going = False
                            break

                        link_elem = article.find_element(By.CSS_SELECTOR, config["link_selector"])
                        post_url = link_elem.get_attribute("href")

                        if post_url in seen_links:
                            continue
                        seen_links.add(post_url)


                        driver.execute_script("window.open(arguments[0]);", post_url)
                        driver.switch_to.window(driver.window_handles[-1])
                        WebDriverWait(driver, 10).until(
                             EC.presence_of_element_located((By.CSS_SELECTOR, config["image_selector"]))
                            )   

                        
                        try:
                            title = driver.find_element(By.CSS_SELECTOR, config["title_selector"]).text.strip()
                        except:
                             title = ""
                        

                        try:
                            img_elem = driver.find_element(By.CSS_SELECTOR, config["image_selector"])
                            img_url = img_elem.get_attribute("src")
                            ocr_result = extract_text_from_image_advanced(img_url)
                            
                            image_text = ocr_result["full_text"]
                            amount_hint = ocr_result["top_right_text"]
                            location_hint = ocr_result["bottom_right_text"]
                            deadline_hint = ocr_result["deadline_text"]
                            
                           
                        except Exception as e:
                            logger.warning(f"No image or OCR failed for '{title}': {e}")
                            image_text = "No image text found"
                            amount_hint = location_hint = deadline_hint = "" 

                        try:
                            deadline = self.extract_deadline(image_text, deadline_hint)
                        except Exception as e:
                            logger.warning(f"Failed to extract deadline for '{title}': {e}")
                            deadline = ""

                        try:
                            location = self.extract_location(image_text, location_hint)
                        except Exception as e:
                            logger.warning(f"Failed to extract location for '{title}': {e}")
                            location = "Unknown"
                        
                        final_url = post_url
                        try:
                            apply_link = self.extract_apply_link(image_text)
                            if apply_link == "No link found":
                                try:
                                    parent_a = img_elem.find_element(By.XPATH, "./ancestor::a[1]")
                                    final_url = parent_a.get_attribute("href") or post_url
                                except Exception:
                                    final_url = post_url
                        except Exception as e:
                            logger.warning(f"Failed to extract apply link for '{title}': {e}")
                            apply_link = ""

                        try:
                            amount = extract_amount(image_text, amount_hint)
                        except Exception as e:
                            logger.warning(f"Failed to extract amount for '{title}': {e}")
                            amount = ""
                        
                        try:
                            emails_found = extract_emails(f"{title} {image_text}")
                        except Exception as e:
                            logger.warning(f"Failed to extract emails for '{title}': {e}")
                            emails_found = []
                        
                        

                        
                        if deadline is None or deadline >= datetime.now(timezone.utc).date():
                            all_opportunities.append({
                                "title": title,
                                "url": final_url,
                                "description": image_text,
                                "grant_amount": ", ".join(amount) if amount else "",
                                "tags": f"{amount if amount else ''}, {location if location else ''}",
                                "deadline": deadline.strftime("%Y-%m-%d") if deadline else "",
                                 "email": ", ".join(emails_found) if emails_found else "",
                            })

                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])

                    except Exception as e:
                        logger.warning(f"PickupTheFlow: Failed to process an article: {e}")
                        driver.switch_to.window(driver.window_handles[0])
                        continue

                if not keep_going:
                    break

        finally:
            if driver:
                get_driver_pool().release_driver(driver)
                logging.info("PickupTheFlow: Scraper finished and driver released.")

        logger.info(f"PickupTheFlow: Scraped {len(all_opportunities)} valid opportunities.")
        return all_opportunities

    def gradual_scroll(self, driver, steps=5, pause=1.0):
        last_height = driver.execute_script("return document.body.scrollHeight")
        for i in range(steps):
            scroll_position = (i + 1) / steps * last_height
            driver.execute_script(f"window.scrollTo(0, {scroll_position});")
            time.sleep(pause)





    def extract_deadline(self, text, hint=None):
        def parse_for_deadline(candidate_text):
            lines = candidate_text.splitlines()
            for i, line in enumerate(lines):
                if "deadline" in line.lower():
                    candidate_lines = " ".join(lines[i:i+3])
                    break
            else:
                candidate_lines = candidate_text

            date_regex = r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|" \
             r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)" \
             r"\s+(?:[1-9]|[12][0-9]|3[01])(?:st|nd|rd|th)?,?\s+\d{4}\b"

            matches = re.findall(date_regex, candidate_lines, flags=re.IGNORECASE)
            for match in matches:
                try:
                    normalized = re.sub(r"(\d{1,2})(st|nd|rd|th)", r"\1", match, flags=re.IGNORECASE)
                    parsed = parser.parse(normalized)
                    if parsed.date() >= datetime.now(timezone.utc).date():
                        return parsed.date()
                    if parsed.day > 31 or parsed.month > 12:
                            continue
                except Exception:
                    continue
            return None

        return parse_for_deadline(hint or "") or parse_for_deadline(text)




        
    def extract_location(self, text, hint=None):
        def parse_locations(text_input):
            doc = nlp(text_input)
            locations = [ent.text.strip() for ent in doc.ents if ent.label_ == "GPE"]
            if locations:
                from collections import Counter
                return Counter(locations).most_common(1)[0][0]

            common_locations = [
                "worldwide", "global", "united states", "usa", "new york",
                "california", "canada", "london", "tokyo", "texas", "chicago"
            ]
            lowered = text_input.lower()
            for loc in common_locations:
                if loc in lowered:
                    return loc.title()

            return None

        return parse_locations(hint or "") or parse_locations(text) or "Unknown"


    
    def extract_apply_link(self, text):
        lines = text.splitlines()

        for i, line in enumerate(lines):
            if "apply" in line.lower() or "info" in line.lower():
                for j in range(i, min(i + 5, len(lines))):  
                    url_match = re.search(r"https?://[^\s\)\]]+", lines[j])
                    if url_match:
                        return url_match.group(0).strip().rstrip(".,;")

        fallback = re.search(r"https?://[^\s\)\]]+", text)
        return fallback.group(0).strip().rstrip(".,;") if fallback else "No link found"



  


