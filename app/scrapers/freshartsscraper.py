import logging
import time
from scrapers.base_scraper import BaseScraper
from utils.driver_pool import get_driver_pool
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

logger = logging.getLogger(__name__)

class FreshArtsScraper(BaseScraper):
    def scrape(self):
        driver = get_driver_pool().get_driver()
        if driver is None:
            logger.error("Could not obtain a webdriver instance.")
            return []

        all_opportunities = []
        config = self.config

        try:
            driver.get(config["url"])

            if config.get("iframe", False):
                try:
                    WebDriverWait(driver, 20).until(
                        EC.frame_to_be_available_and_switch_to_it((By.TAG_NAME, "iframe"))
                    )
                    logger.info("✅ Switched to iframe.")
                except TimeoutException:
                    driver.save_screenshot("/tmp/iframe_not_found.png")
                    logger.error("❌ Could not find or switch to iframe — screenshot saved.")
                    return []

            
            if config.get("scroll", False):
                for y in range(0, 10000, 1000):
                    driver.execute_script(f"window.scrollTo(0, {y});")
                    time.sleep(0.5)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(1)

            
            def click_tab_and_extract(label):
                try:
                    tab = WebDriverWait(driver, 20).until(
                        EC.element_to_be_clickable((By.XPATH, f'//p[text()="{label}"]/ancestor::div[contains(@class, "opportunity-categories-item")]'))
                    )
                    driver.execute_script("arguments[0].scrollIntoView(true);", tab)
                    time.sleep(1)
                    tab.click()
                    logger.info(f"✅ Clicked '{label}' tab.")
                except TimeoutException:
                    driver.save_screenshot(f"/tmp/{label.lower().replace(' ', '_')}_click_fail.png")
                    logger.error(f"❌ Could not find '{label}' tab — screenshot saved.")
                    return []

                
                WebDriverWait(driver, 20).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, config["opportunity_selector"]))
                )
                time.sleep(2)

                items = driver.find_elements(By.CSS_SELECTOR, config["opportunity_selector"])
                logger.info(f"🔍 Found {len(items)} items under '{label}'.")

                opportunities = []
                for item in items:
                    try:
                        if not item.find_elements(By.CLASS_NAME, config["card_class"]):
                            continue

                        card = item.find_element(By.CLASS_NAME, config["card_class"])
                        partial_link = card.get_attribute("href")
                        full_url = config["url"].split("/artist")[0] + partial_link if partial_link else ""

                        title = card.find_element(By.CLASS_NAME, config["title_class"]).text.strip()
                        description = card.find_element(By.CLASS_NAME, config["description_class"]).text.strip()
                        tags = card.find_element(By.CSS_SELECTOR, config["tags_selector"]).text.strip()

                        deadline = ""
                        email = ""
                        for p in card.find_elements(By.TAG_NAME, "p"):
                            if "Closing on" in p.text:
                                deadline = p.text.strip()
                            if "@" in p.text:
                                email = p.text.strip()

                        opportunities.append({
                            "title": title,
                            "url": full_url,
                            "description": description,
                            "tags": tags,
                            "deadline": deadline,
                            "email": email
                        })

                    except Exception as e:
                        logger.warning(f"❌ Error parsing opportunity card: {e}")

                logger.info(f"✅ Scraped {len(opportunities)} '{label}' opportunities.")
                return opportunities

            
            for tab in config.get("tabs", []):
                label = tab["label"]
                all_opportunities.extend(click_tab_and_extract(label))

        finally:
            if driver:
                get_driver_pool().release_driver(driver)

        logger.info(f"🎯 Total opportunities scraped: {len(all_opportunities)}")
        return all_opportunities
