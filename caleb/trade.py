from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time

# Path to ChromeDriver
CHROMEDRIVER_PATH = r"F:\Desktop\chromedriver-win64\chromedriver.exe"  # Update this!

chrome_options = Options()
chrome_options.debugger_address = "localhost:9222"  # Attach to open Chrome

# Connect Selenium to the existing Chrome session
driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=chrome_options)

print("Connected to:", driver.current_url)

# Now you can automate actions
driver.get("https://kalshi.com/markets/kxhighchi/highest-temperature-in-chicago")



x