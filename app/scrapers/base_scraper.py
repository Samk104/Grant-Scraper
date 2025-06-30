from abc import ABC, abstractmethod

class BaseScraper(ABC):
    def __init__(self, config):
        self.config = config

    @abstractmethod
    def scrape(self):
        pass
