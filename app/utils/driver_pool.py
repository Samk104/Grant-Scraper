import random
import threading
import time
import logging
import json
import os
from queue import Queue
from selenium import webdriver
from selenium.webdriver import ChromeOptions
from selenium.webdriver.remote.webdriver import WebDriver
from typing import Optional, Dict, List
from selenium.webdriver.remote.remote_connection import RemoteConnection
from contextlib import contextmanager

logger = logging.getLogger(__name__)

visited_urls_lock = threading.Lock()

class DriverPool:
    def __init__(self, min_drivers: int = 2, max_drivers: int = 6):
        self.min_drivers = min_drivers
        self.max_drivers = max_drivers
        self.active_drivers = 0
        self.lock = threading.Lock()
        self.drivers = Queue()
        for _ in range(self.min_drivers):
            driver = self._create_driver()
            if driver:
                self.drivers.put(driver)
                self.active_drivers += 1
        logger.info(f"Initialized driver pool with {self.min_drivers} min, {self.max_drivers} max drivers")
        
        if self.active_drivers == 0:
            logger.warning("No drivers could be initialized during startup.")


    def _create_driver(self) -> Optional[WebDriver]:
        max_retries = 3
        retry_delay = 2 
        RemoteConnection.set_timeout(20) 

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Driver Pool: Attempt {attempt}/{max_retries} - Creating Remote Chrome driver")
                options = ChromeOptions()
                options.add_argument('--headless')
                options.add_argument('--disable-gpu')
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--enable-javascript')
                options.add_argument('--disable-infobars')

                # Anti-bot fingerprinting
                user_agent = (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                options.add_argument(f'user-agent={user_agent}')
                options.add_argument('--disable-blink-features=AutomationControlled')
                options.add_experimental_option('excludeSwitches', ['enable-automation'])
                options.add_experimental_option('useAutomationExtension', False)

                # Random window size
                width = random.randint(1200, 1600)
                height = random.randint(800, 1000)
                options.add_argument(f'--window-size={width},{height}')

                driver = webdriver.Remote(
                    command_executor='http://selenium-hub:4444/wd/hub',
                    options=options
                )
                driver.set_page_load_timeout(30)

                driver.execute_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )

                if driver.session_id and self.is_driver_healthy(driver):
                    logger.info("Driver successfully created and session started.")
                    return driver
                else:
                    logger.error("Driver session_id is None. Discarding driver.")
                    driver.quit()

            except Exception as e:
                logger.error(f"Driver Pool: Driver creation failed on attempt {attempt}/{max_retries}: {e}")

            time.sleep(retry_delay) 

        logger.critical("Driver Pool: All driver creation attempts failed after retries.")
        return None

            
            
    def is_driver_healthy(self, driver: WebDriver) -> bool:
        try:
            driver.title 
            return True
        except Exception as e:
            logger.debug(f"Driver failed health check: {e}")
            return False


    
    
    def get_driver(self) -> Optional[webdriver.Chrome]:
        start_time = time.time()
        while time.time() - start_time < 30:
            with self.lock:
                driver = None

                if not self.drivers.empty():
                    driver = self.drivers.get()
                    logger.info(f"Pulled driver from pool. Active: {self.active_drivers}, Queue: {self.drivers.qsize()}")
                    if self.is_driver_healthy(driver):
                        logger.info("Driver passed health check")
                        return driver
                    else:
                        logger.warning("Driver Pool: Driver failed health check. Discarding.")
                        try:
                            driver.quit()
                        except Exception as e:
                            logger.warning(f"Error while quitting driver: {e}")
                        self.active_drivers -= 1
                        driver = None

                if self.active_drivers < self.max_drivers:
                    logger.info(f"Pool not full (Active: {self.active_drivers}/{self.max_drivers}). Creating new driver...")
                    driver = self._create_driver()
                    if driver:
                        self.active_drivers += 1
                        logger.info(f"Driver Pool: New driver created. Active drivers now: {self.active_drivers}")
                        return driver
                    else:
                        logger.error("Driver Pool: Failed to create new driver")
                else:
                    logger.info(f"Driver Pool: Pool at capacity ({self.active_drivers}/{self.max_drivers}). Waiting...")

            time.sleep(0.5)

        logger.warning(f"Driver Pool: No drivers available after 30s wait. Active: {self.active_drivers}, Queue: {self.drivers.qsize()}")
        return None


    def release_driver(self, driver: Optional[webdriver.Chrome]):
        with self.lock:
            if driver is None:
                logger.warning("Driver Pool: release_driver called with None")
                return

            try:
                session_ok = bool(getattr(driver, "session_id", None))
                if self.is_driver_healthy(driver) and session_ok:
                    self.drivers.put(driver)
                    logger.debug("Driver released back to pool")
                else:
                    logger.warning("Driver unhealthy on release. Discarding...")
                    try:
                        driver.quit()
                    except Exception as e:
                        if "session with ID" in str(e) or "invalid session id" in str(e).lower():
                            logger.debug(f"Driver already invalidated during release: {e}")
                        else:
                            logger.warning(f"Error while quitting driver during release: {e}")
                    finally:
                        self.active_drivers = max(0, self.active_drivers - 1)

            except Exception as e:
                logger.error(f"Error in release_driver: {e}")

    
    def reset_driver(self, old_driver: Optional[webdriver.Chrome]) -> Optional[webdriver.Chrome]:
        with self.lock:
            if old_driver:
                try:
                    old_driver.quit()
                except Exception as e:
                    logger.warning(f"Failed to quit old driver: {e}")
                finally:
                    self.active_drivers = max(0, self.active_drivers - 1)

            driver = self._create_driver()
            if driver:
                self.active_drivers += 1
                logger.info(f"Driver successfully reset. Active: {self.active_drivers}")
                return driver
            else:
                logger.warning("Failed to reset driver")
                return None



    def close(self):
        with self.lock:
            while not self.drivers.empty():
                driver = self.drivers.get()
                try:
                    driver.quit()
                except Exception as e:
                    if "session with ID" in str(e) or "invalid session id" in str(e).lower():
                        logger.debug(f"Driver Pool: Driver already invalidated during shutdown: {e}")
                    else:
                        logger.warning(f"Driver Pool: Error quitting driver during pool shutdown: {e}")
                finally:
                    self.active_drivers = max(0, self.active_drivers - 1)

            logger.info("Driver Pool: All drivers closed and pool cleared.")




_driver_pool: Optional[DriverPool] = None

def init_driver_pool(min_drivers: int = 2, max_drivers: int = 6):
    global _driver_pool
    if _driver_pool is None:
        _driver_pool = DriverPool(min_drivers, max_drivers)
        logger.info("Global driver_pool initialized")


def get_driver_pool() -> DriverPool:
    if _driver_pool is None:
        raise RuntimeError("Driver pool not initialized. Call init_driver_pool() in run.py.")
    return _driver_pool


@contextmanager
def borrow_driver(max_attempts: int = 3, backoff: float = 1.0):
    pool = get_driver_pool()
    driver = None
    try:
        for attempt in range(1, max_attempts + 1):
            driver = pool.get_driver()
            if driver is None:
                logger.warning("borrow_driver: no driver available; retrying...")
                time.sleep(backoff * attempt)

            if pool.is_driver_healthy(driver):
                break

            logger.warning("borrow_driver: got an unhealthy driver; recycling and retrying...")
            try:
                pool.reset_driver(driver)
            except Exception:
                logger.exception("borrow_driver: failed to reset driver")
            driver = None
            time.sleep(backoff * attempt)

        if driver is None:
            logger.exception("borrow_driver: driver is none, failed to reset driver")
            raise RuntimeError("Failed to acquire a healthy webdriver from the pool")

        yield driver

    finally:
        if driver is not None:
            pool.release_driver(driver)


def check_driver_pool_integrity(pool: DriverPool):
    with pool.lock:
        queue_size = pool.drivers.qsize()
        active = pool.active_drivers
        total_estimated = queue_size 

        all_queued = list(pool.drivers.queue)

        for i, driver in enumerate(all_queued):
            if not pool.is_driver_healthy(driver):
                logger.warning(f"Driver #{i} in queue is unhealthy!")

        logger.info(f"Integrity check → Active: {active}, Queue Size: {queue_size}")

        if active < 0:
            logger.error("Driver Pool: ERROR: active_drivers is negative!")
        elif active < queue_size:
            logger.error("Driver Pool: ERROR: More drivers in queue than tracked active drivers!")
        elif active > queue_size + (pool.max_drivers - pool.min_drivers):
            logger.error("Driver Pool: ERROR: active_drivers exceeds expected bounds!")
        else:
            logger.info("DriverPool integrity looks good.")
