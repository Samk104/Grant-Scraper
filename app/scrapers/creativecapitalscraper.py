import logging
import time
from app.scrapers.base_scraper import BaseScraper
from app.utils.driver_pool import get_driver_pool
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger(__name__)

class CreativeCapitalScraper(BaseScraper):
    def scrape(self):
        driver = get_driver_pool().get_driver()
        if driver is None:
            logger.error("CreativeCapital: Could not obtain a webdriver instance.")
            return []

        all_opportunities = []
        config = self.config

        try:
            driver.get(config["url"])
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "filter-desktop"))
            )

            try:
                driver.find_element(By.ID, "desktop-grant")
                checkbox_ids = ["desktop-grant", "desktop-texas"]
                logger.info("CreativeCapital: Detected desktop layout - using desktop checkboxes")
            except:
                checkbox_ids = ["mob-grant", "mob-texas"]
                logger.info("CreativeCapital: Detected mobile layout - using mobile checkboxes")

            if checkbox_ids[0].startswith("desktop"):
                accordion_ids = ["#collapseOne2", "#collapseTwo2"]
                for acc_id in accordion_ids:
                    try:
                        section = driver.find_element(By.CSS_SELECTOR, acc_id)
                        if "show" not in section.get_attribute("class"):
                            toggle_btn = driver.find_element(By.CSS_SELECTOR, f"[data-bs-target='{acc_id}']")
                            driver.execute_script("arguments[0].scrollIntoView(true);", toggle_btn)
                            time.sleep(0.3)
                            driver.execute_script("arguments[0].click();", toggle_btn)
                            time.sleep(0.5)
                            logger.info(f"CreativeCapital: Expanded accordion: {acc_id}")
                    except Exception as e:
                        logger.warning(f"CreativeCapital: Failed to expand accordion '{acc_id}': {e}")

            for checkbox_id in checkbox_ids:
                try:
                    logger.info(f"CreativeCapital: Waiting for checkbox '{checkbox_id}' to be clickable...")
                    checkbox = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.ID, checkbox_id))
                    )

                    if not checkbox.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView(true);", checkbox)
                        time.sleep(0.5)

                    if not checkbox.is_selected():
                        driver.execute_script("arguments[0].click();", checkbox)
                        logger.info(f"CreativeCapital: Clicked checkbox: {checkbox_id}")
                    else:
                        logger.info(f"CreativeCapital: Checkbox '{checkbox_id}' already selected, skipping click")
                except Exception as e:
                    logger.warning(f"CreativeCapital: Could not click checkbox '{checkbox_id}': {e}")


            logger.info("CreativeCapital: Filters applied, waiting for page to load...")
            time.sleep(2)

            logger.info("CreativeCapital: Starting to scrape opportunities")
            while True:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.item"))
                )
                items = driver.find_elements(By.CSS_SELECTOR, "a.item")
                logger.info(f"CreativeCapital: Found {len(items)} opportunities on current page")

                for item in items:
                    try:
                        title = item.find_element(By.CSS_SELECTOR, ".item-title h3").text.strip()
                        description = item.find_element(By.CSS_SELECTOR, ".item-desc p").text.strip()
                        deadline = item.find_element(By.CSS_SELECTOR, ".item-info span").text.strip()
                        url = item.get_attribute("href")

                        opp = {
                            "title": title,
                            "description": description,
                            "deadline": deadline.replace("DEADLINE:", "").strip(),
                            "url": url,
                            "source": config["url"]
                        }
                        all_opportunities.append(opp)
                    except Exception as e:
                        logger.warning(f"CreativeCapital:  Error parsing opportunity: {e}")

                try:
                    next_btn = driver.find_element(By.CSS_SELECTOR, ".pagination-btn.next")
                    next_page = next_btn.get_attribute("data-page")
                    if "disabled" in next_btn.get_attribute("class") or not next_page:
                        break
                    driver.execute_script("arguments[0].click();", next_btn)
                    time.sleep(2)
                except Exception:
                    logger.info("CreativeCapital: No pagination or next page found.")
                    break

        finally:
            get_driver_pool().release_driver(driver)

        logger.info(f"CreativeCapital: Total scraped: {len(all_opportunities)}")
        return all_opportunities
