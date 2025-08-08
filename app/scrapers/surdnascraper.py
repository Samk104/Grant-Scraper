import logging
import time
from app.scrapers.base_scraper import BaseScraper
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from app.utils.extractors import extract_amount, extract_emails 

logger = logging.getLogger(__name__)

class SurdnaScraper(BaseScraper):
    def scrape(self, driver):
        if driver is None:
            logger.error("Surdna: Could not obtain a webdriver instance.")
            return []

        all_opportunities = []
        config = self.config


        page = 1
        while True:
            if page == 1:
                url = config['url']
            else:
                url = f"{config['url'].rstrip('/')}/page/{page}/"
            logger.info(f"Surdna: Loading Surdna grants page {page} -> {url}")
            driver.get(url)

            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, config["row_selector"]))
                )
            except Exception as e:
                logger.warning(f"Surdna: No table rows found on page {page}: {e}")
                break

            rows = driver.find_elements(By.CSS_SELECTOR, config["row_selector"])
            logger.info(f"Surdna: Found {len(rows)} rows on page {page}")

            if not rows:
                break

            for i, row in enumerate(rows, start=1):
                try:
                    cols = row.find_elements(By.TAG_NAME, config["cell_tag"])
                    if len(cols) < 5:
                        continue

                    year = cols[0].text.strip()
                    org_col = cols[1]
                    status = cols[2].text.strip()
                    amount = cols[3].text.strip()
                    duration = cols[4].text.strip()

                    if status.lower() != "active":
                        continue

                    org_links = org_col.find_elements(By.CSS_SELECTOR, config["org_link_selector"])
                    if org_links:
                        org_link = org_links[0]
                        title = org_link.text.strip()
                        link_url = org_link.get_attribute("href")
                    else:
                        title = org_col.text.strip().split("\n")[0] or "No title found"
                        link_url = "No URL found"
                        logger.warning(f"Surdna: Missing <a> tag in row {i} on page {page}. Raw org cell: '{org_col.text.strip()}'")

                    description_elem = org_col.find_elements(By.CSS_SELECTOR, config["description_selector"])
                    description = description_elem[0].text.strip() if description_elem else "No description provided"
                    description += f"\n\nAmount: {amount}, Duration: {duration}, Year: {year}"
                    
                    full_text = f"{title} {description}"
                    emails_found = extract_emails(full_text)
                    amounts_found = extract_amount(full_text)
                    
                    deadline = ""

                    opp = {
                        "title": title,
                        "url": link_url,
                        "description": description,
                        "grant_amount": ", ".join(amounts_found) if amounts_found else "",
                        "tags": f"{amount}, {duration}, {year}",
                        "deadline": deadline,
                        "email": ", ".join(emails_found) if emails_found else "",
                    }
                    all_opportunities.append(opp)
                except Exception as e:
                    logger.warning(f"Surdna: Failed to parse row {i} on page {page}: {e}")

            try:
                next_btn_exists = driver.find_element(By.CSS_SELECTOR, config["next_button_selector"])
                if next_btn_exists:
                    page += 1
                    time.sleep(1.5)
                else:
                    logger.info("Surdna: No next button found. Done.")
                    break
            except Exception:
                logger.info("Surdna: No next button found. Done.")
                break


        logger.info(f"Surdna: Total scraped: {len(all_opportunities)}")
        return all_opportunities
