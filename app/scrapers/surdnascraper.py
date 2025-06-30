import logging
import time
from scrapers.base_scraper import BaseScraper
from utils.driver_pool import get_driver_pool
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger(__name__)

class SurdnaScraper(BaseScraper):
    def scrape(self):
        driver = get_driver_pool().get_driver()
        if driver is None:
            logger.error("Could not obtain a webdriver instance.")
            return []

        all_opportunities = []
        config = self.config

        try:
            page = 1
            while True:
                if page == 1:
                    url = config['url']
                else:
                    url = f"{config['url'].rstrip('/')}/page/{page}/"
                logger.info(f"Loading Surdna grants page {page} -> {url}")
                driver.get(url)

                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr"))
                    )
                except Exception as e:
                    logger.warning(f"No table rows found on page {page}: {e}")
                    break

                rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
                logger.info(f"Found {len(rows)} rows on page {page}")

                if not rows:
                    break

                for i, row in enumerate(rows, start=1):
                    try:
                        cols = row.find_elements(By.TAG_NAME, "td")
                        if len(cols) < 5:
                            continue

                        year = cols[0].text.strip()
                        org_col = cols[1]
                        status = cols[2].text.strip()
                        amount = cols[3].text.strip()
                        duration = cols[4].text.strip()

                        if status.lower() != "active":
                            continue

                        org_links = org_col.find_elements(By.CSS_SELECTOR, "a")
                        if org_links:
                            org_link = org_links[0]
                            title = org_link.text.strip()
                            link_url = org_link.get_attribute("href")
                        else:
                            title = org_col.text.strip().split("\n")[0] or "No title found"
                            link_url = "No URL found"
                            logger.warning(f"Missing <a> tag in row {i} on page {page}. Raw org cell: '{org_col.text.strip()}'")

                        description_elem = org_col.find_elements(By.CSS_SELECTOR, ".project-summary p")
                        description = description_elem[0].text.strip() if description_elem else "No description provided"
                        description += f"\n\nAmount: {amount}, Duration: {duration}, Year: {year}"

                        opp = {
                            "title": title,
                            "description": description,
                            "deadline": None,
                            "url": link_url,
                            "source": config["url"],
                            "tags": f"{amount}, {duration}, {year}"
                        }
                        all_opportunities.append(opp)
                    except Exception as e:
                        logger.warning(f"Failed to parse row {i} on page {page}: {e}")

                try:
                    next_btn = driver.find_element(By.CSS_SELECTOR, "a.next.page-numbers")
                    if next_btn:
                        page += 1
                        time.sleep(1.5)
                    else:
                        logger.info("No next button found. Done.")
                        break
                except:
                    logger.info("No next button found. Done.")
                    break

        finally:
            get_driver_pool().release_driver(driver)

        logger.info(f"Total scraped: {len(all_opportunities)}")
        return all_opportunities
