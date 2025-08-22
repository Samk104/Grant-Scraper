import sys
import time
import os
import yaml
import logging
import threading
import importlib
from datetime import datetime, timezone
import json

from app.utils.driver_pool import check_driver_pool_integrity, init_driver_pool, get_driver_pool
from app.db import init_db, SessionLocal
from app.db.save_opportunities import save_opportunities
from app.utils.driver_pool import borrow_driver
from app.utils.rag.keyword_matcher import validate_synonyms
from app.utils.rag.config import load_system_prompt
from app.utils.rag.config import get_keywords

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

MAX_RETRIES = 3
MAX_THREADS = 6


def run_all_scrapers(config_path: str | None = None) -> dict:
    setup_logging()
    logger = logging.getLogger(__name__)
    try:
        startup_checks()
    except Exception as e:
        logger.error("Startup checks failed: %s", e, exc_info=True)
        raise

    time.sleep(10)

    init_db()
    init_driver_pool()

    try:
        if config_path:
            with open(config_path, "r") as f:
                config_data = yaml.safe_load(f)
        else:
            config_data = load_config()

        config_map = build_config_map(config_data)
        scrape_and_store_all_sites_concurrently(config_map)

        return {"status": "ok", "sites": len(config_map)}
    finally:
        try:
            check_driver_pool_integrity(get_driver_pool())
            get_driver_pool().close()
        except Exception:
            logger.warning("Driver pool close encountered an issue.", exc_info=True)
        logger.info("Runner: Scraping job complete, all resources shut down.")




def startup_checks():
    load_system_prompt()
    invalid = validate_synonyms(strict=False)
    if invalid:
        logger.warning(f"Found invalid synonyms not in keywords.core: {invalid}")
    
    core_keywords = get_keywords().get("core", [])

    if not core_keywords:
        raise ValueError("keywords.core is empty — please define at least one keyword.")

    if not all(isinstance(k, str) and k.strip() for k in core_keywords):
        raise ValueError("keywords.core must contain only non-empty strings.")

    logger.info(f"Startup check: {len(core_keywords)} core keywords loaded.")

def load_config():
    config_path = os.path.join(os.getcwd(), "app", "configs", "sites_config.yml")
    logger.info(f"Runner: Loading site config from: {config_path}")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)

def build_config_map(configs):
    return {site["name"]: site for site in configs["sites"]}

def write_backup(site_name: str, data: list[dict]):
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    os.makedirs("backups", exist_ok=True)
    filename = f"backups/{site_name}_{timestamp}.json"
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Runner: Backup written: {filename}")
    except Exception as e:
        logger.error(f"Runner: Failed to write backup for {site_name}: {e}")

def get_scraper_instance(class_name: str, config: dict):
    try:
        module = importlib.import_module(f"app.scrapers.{class_name.lower()}")
        scraper_class = getattr(module, class_name)
        return scraper_class(config)
    except (ModuleNotFoundError, AttributeError) as e:
        logger.warning(f"Runner: Could not find scraper '{class_name}', falling back to GenericOpportunityScraper: {e}")
        try:
            from app.scrapers.genericscraper import GenericScraper  
            return GenericScraper(config)  
        except Exception as ge:
            logger.error(f"Runner: GenericScraper fallback also failed: {ge}")
            return None

def scrape_site(site_name: str, site_config: dict):
    logger.info(f"Runner: Thread started for site: {site_name}")
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with borrow_driver() as driver:
                class_name = site_config.get("scraper_class", "GenericOpportunityScraper")
                scraper = get_scraper_instance(class_name, site_config)
            
                
                opportunities = scraper.scrape(driver)
                logger.info(f"Runner: Scraped {len(opportunities)} opportunities from '{site_name}'")
                
                with SessionLocal() as db:
                    saved = save_opportunities(opportunities, db, source=site_config["url"])
                    logger.info(f"Runner: Saved {saved} new unique entries from '{site_name}'")

                write_backup(site_name, opportunities)
            break
        except Exception as e:
            logger.warning(f"Runner: Attempt {attempt}/{MAX_RETRIES} failed for '{site_name}': {e}")
            if attempt == MAX_RETRIES:
                logger.error(f"Runner: All retries failed for '{site_name}'", exc_info=True)
            else:
                time.sleep(min(3, attempt))
        

def scrape_and_store_all_sites_concurrently(config_map: dict):
    threads = []
    semaphore = threading.Semaphore(MAX_THREADS)

    def thread_wrapper(site_name, site_config):
        with semaphore:
            scrape_site(site_name, site_config)

    for site_name, site_config in config_map.items():
        t = threading.Thread(target=thread_wrapper, args=(site_name, site_config), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

if __name__ == "__main__":
    try:
        startup_checks()
    except Exception as e:
        logger.error("Startup checks failed: %s", e, exc_info=True)
        raise
    
    time.sleep(10)
    init_db()
    init_driver_pool()

    config_data = load_config()
    config_map = build_config_map(config_data)

    scrape_and_store_all_sites_concurrently(config_map)

    check_driver_pool_integrity(get_driver_pool())
    get_driver_pool().close()
    logger.info("Runner: Scraping job complete, all resources shut down.")
