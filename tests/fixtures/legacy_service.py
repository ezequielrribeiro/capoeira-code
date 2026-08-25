import os
from pathlib import Path
import requests as rq


class LegacyService:
    def fetch(self, url):
        data = rq.get(url)
        return data.text

    async def load(self, key):
        value = os.getenv(key, "")
        return value


def helper(value):
    return value * 2


def main():
    service = LegacyService()
    return service
