import logging
import time
from urllib.parse import urljoin
from app.scrapers.base_scraper import BaseScraper
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException 
from app.utils.extractors import extract_amount
from app.utils.extractors import extract_emails
from dateutil.parser import parse
import re

logger = logging.getLogger(__name__)

class FreshArtsScraper(BaseScraper):
    def scrape(self, driver):
        
        if driver is None:
            logger.error("FreshArts: Could not obtain a webdriver instance.")
            return []

        all_opportunities = []


        driver.get(self.config["url"])

        if self.config.get("iframe", False):
            try:
                WebDriverWait(driver, 20).until(
                    EC.frame_to_be_available_and_switch_to_it((By.TAG_NAME, "iframe"))
                )
                logger.info("FreshArts: Switched to iframe.")
            except TimeoutException:
                driver.save_screenshot("/tmp/iframe_not_found.png")
                logger.error("FreshArts: Could not find or switch to iframe - screenshot saved.")
                return []

        
        if self.config.get("scroll", False):
            for y in range(0, 10000, 1000):
                driver.execute_script(f"window.scrollTo(0, {y});")
                time.sleep(0.5)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

        
        def click_tab_and_extract(label):
            try:
                tab = WebDriverWait(driver, 20).until(
                    EC.element_to_be_clickable((By.XPATH, f'//p[contains(text(), "{label}")]/parent::div'))
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", tab)
                time.sleep(1)
                tab.click()
                logger.info(f"FreshArts: Clicked '{label}' tab.")
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
            except TimeoutException:
                driver.save_screenshot(f"/tmp/{label.lower().replace(' ', '_')}_click_fail.png")
                logger.error(f"FreshArts: Could not find '{label}' tab — screenshot saved.")
                return []

            
            WebDriverWait(driver, 20).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, self.config["opportunity_selector"]))
            )
            time.sleep(2)

            items = driver.find_elements(By.CSS_SELECTOR, self.config["opportunity_selector"])
            logger.info(f"FreshArts: Found {len(items)} items under '{label}'.")

            opportunities = []
            for item in items:
                try:
                    if not item.find_elements(By.CLASS_NAME, self.config["card_class"]):
                        continue

                    card = item.find_element(By.CLASS_NAME, self.config["card_class"])
                    partial_url = card.get_attribute("href") or ""
                    full_url =  urljoin(self.config['opportunity_base_url'], partial_url)

                    title = card.find_element(By.CLASS_NAME, self.config["title_class"]).text.strip()
                    description = card.find_element(By.CLASS_NAME, self.config["description_class"]).text.strip()
                    tags = card.find_element(By.CSS_SELECTOR, self.config["tags_selector"]).text.strip()
                    
                    amounts_found = extract_amount(f"{title} {description} {tags}")

                    deadline = ""
                    email = ""
                    apply_link = "" 

                    
                    for p in card.find_elements(By.TAG_NAME, "p"):
                        if "Closing on" in p.text:
                            deadline = p.text.strip()
                        if "@" in p.text:
                            email = p.text.strip()
                    
                    driver.execute_script("window.open(arguments[0]);", full_url)  
                    driver.switch_to.window(driver.window_handles[-1])  
                    
                    try:
                        
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CLASS_NAME, "event-info")) 
                        )
                        container = driver.find_element(By.CLASS_NAME, "event-info")
                        blocks = container.find_elements(By.CLASS_NAME, "border")
                        
                        final_email = ""
                        raw_date = ""
                        email_text = ""
                        for block in blocks:
                            label_text = block.find_element(By.TAG_NAME, "span").text.strip().lower()
                            content_div = block.find_element(By.TAG_NAME, "div")

                            if "when" in label_text:
                                try:
                                    raw_date = content_div.find_element(By.TAG_NAME, "p").text.strip()
                                    parsed = parse(raw_date, fuzzy=True, ignoretz=True)
                                    deadline = parsed.strftime("%Y-%m-%d")
                                except:
                                    logger.warning(f"FreshArts: Failed to parse date from '{raw_date}' for {full_url}")

                
                            elif "contact" in label_text:
                                try:
                                    email_text = content_div.find_element(By.TAG_NAME, "p").text.strip()
                                    emails = extract_emails(email_text)
                                    final_email = emails[0] if emails else email
                                except:
                                    logger.warning(f"FreshArts: Failed to extract email from '{email_text}' for {full_url}")

                            elif "apply" in label_text:
                                try:
                                    apply_link = content_div.find_element(By.TAG_NAME, "a").get_attribute("href")
                                except:
                                    logger.warning(f"FreshArts: Failed to extract apply link for {full_url}")
                        
                        description_html = description or ""
                        try:
                            desc_container = WebDriverWait(driver, 10).until(
                                        EC.presence_of_element_located((By.CLASS_NAME, "description"))
                                    )
                            paragraphs = desc_container.find_elements(By.TAG_NAME, "p")

                            clean_paragraphs = []
                            for p in paragraphs:
                                raw = p.text.strip()
                                if raw:
                                    clean = re.sub(r"\s+", " ", raw).strip()
                                    clean_paragraphs.append(clean)

                            description_html = "\n".join(clean_paragraphs)

                        except Exception as e:
                            logger.warning(f"FreshArts: Could not extract full description from {full_url}: {e}")
                            

                    except Exception as e:
                        logger.warning(f"FreshArts: Failed to extract detail page for {full_url}: {e}")
                    finally:
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])
                        if self.config.get("iframe", False):
                            try:
                                WebDriverWait(driver, 20).until(
                                    EC.frame_to_be_available_and_switch_to_it((By.TAG_NAME, "iframe"))
                                )
                            except TimeoutException:
                                driver.save_screenshot("/tmp/iframe_not_found.png")
                                logger.error("FreshArts: Could not find or switch to iframe after coming back from details - screenshot saved.")
                                continue
                    
                    



                    opportunities.append({
                        "title": title,
                        "url": apply_link if apply_link else full_url,
                        "description": description_html or description,
                        "grant_amount": ", ".join(amounts_found) if amounts_found else "",
                        "tags": tags,
                        "deadline": deadline,
                        "email": final_email if final_email else "",
                    })

                except Exception as e:
                    logger.warning(f"FreshArts: Error parsing opportunity card: {e}")

            logger.info(f"FreshArts: Scraped {len(opportunities)} '{label}' opportunities.")
            return opportunities

        
        for tab in self.config.get("tabs", []):
            label = tab["label"]
            all_opportunities.extend(click_tab_and_extract(label))

        logger.info(f"FreshArts: Total opportunities scraped: {len(all_opportunities)}")
        return all_opportunities
    