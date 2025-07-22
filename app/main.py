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

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

MAX_RETRIES = 3
MAX_THREADS = 6

def load_config():
    config_path = os.path.join(os.getcwd(), "app", "configs", "sites_config.yml")
    logger.info(f"📥 Loading site config from: {config_path}")
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
        logger.info(f"💾 Backup written: {filename}")
    except Exception as e:
        logger.error(f"❌ Failed to write backup for {site_name}: {e}")

def get_scraper_instance(class_name: str, config: dict):
    try:
        module = importlib.import_module(f"app.scrapers.{class_name.lower()}")
        scraper_class = getattr(module, class_name)
        return scraper_class(config)
    except (ModuleNotFoundError, AttributeError) as e:
        logger.warning(f"Could not find scraper '{class_name}', falling back to GenericOpportunityScraper: {e}")
        from app.scrapers.freshartsscraper import GenericOpportunityScraper
        return GenericOpportunityScraper(config)

def scrape_site(site_name: str, site_config: dict):
    logger.info(f"Thread started for site: {site_name}")
    with SessionLocal() as db:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                class_name = site_config.get("scraper_class", "GenericOpportunityScraper")
                scraper = get_scraper_instance(class_name, site_config)
                opportunities = scraper.scrape()

                logger.info(f"🧹 Scraped {len(opportunities)} opportunities from '{site_name}'")

                saved = save_opportunities(opportunities, db, source=site_config["url"])
                logger.info(f"✅ Saved {saved} new unique entries from '{site_name}'")

                write_backup(site_name, opportunities)
                break
            except Exception as e:
                logger.warning(f"⚠️ Attempt {attempt}/{MAX_RETRIES} failed for '{site_name}': {e}")
                if attempt == MAX_RETRIES:
                    logger.error(f"❌ All retries failed for '{site_name}'", exc_info=True)

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
    time.sleep(10)
    init_db()
    init_driver_pool()

    config_data = load_config()
    config_map = build_config_map(config_data)

    scrape_and_store_all_sites_concurrently(config_map)

    check_driver_pool_integrity(get_driver_pool())
    get_driver_pool().close()
    logger.info("🛑 Scraping job complete, all resources shut down.")
