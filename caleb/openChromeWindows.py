from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time

market_url  = "https://demo.kalshi.co/markets/kxwiscotus/wi-state-supreme-court"

import subprocess
import time


chrome_path = r"C:\Users\caleb\AppData\Local\Google\Chrome\Application\chrome.exe"


subprocess.Popen([
    chrome_path, 
    "--remote-debugging-port=9222", 
    "--user-data-dir=C:\\selenium_chrome_profile"
], shell=False)


time.sleep(5)
