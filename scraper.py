from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
import time
import re

def market_maker():
    driver = webdriver.Chrome()
    driver.get("https://kalshi.com/markets/kxhighny/highest-temperature-in-nyc")
    time.sleep(5)

    # log in
    # nav = driver.find_element(By.TAG_NAME, 'nav')
    # login_button = nav.find_element(By.CLASS_NAME, 'button-0-1-15')
    # login_span = login_button.find_element(By.CLASS_NAME, 'tabular-nums')
    # login_button.click()

    while True:
        markets = driver.find_elements(By.CLASS_NAME, 'binaryMarketTile-0-1-228')
        for market in markets:
            # label
            label = market.find_element(By.CLASS_NAME, 'flex').get_attribute("innerHTML")

            # yes price
            try:
                yes_button = market.find_element(By.CLASS_NAME, 'yes-0-1-166')
            except Exception as e:
                yes_button = market.find_element(By.CLASS_NAME, 'yes-0-1-151')
            yes_span1 = yes_button.find_element(By.CLASS_NAME, 'tabular-nums')
            yes_text = yes_span1.find_element(By.CLASS_NAME, 'tabular-nums').get_attribute("innerHTML")
            yes_price_text = yes_span1.find_elements(By.CLASS_NAME, 'tabular-nums')[-1].get_attribute("innerHTML")

            print(f"\n{label}")
            print("Text:", yes_text)
            print("Price:", yes_price_text)

            # no price
            no_button = market.find_element(By.CLASS_NAME, 'no-0-1-167')
            no_span1 = no_button.find_element(By.CLASS_NAME, 'tabular-nums')
            no_text = no_span1.find_element(By.CLASS_NAME, 'tabular-nums').get_attribute("innerHTML")
            no_price_text = no_span1.find_elements(By.CLASS_NAME, 'tabular-nums')[-1].get_attribute("innerHTML")

            print("Text:", no_text)
            print("Price:", no_price_text)
            if yes_price_text == "":
                yes_price_text = "0"
            if no_price_text == "":
                no_price_text = "0"
            yes_price = int(re.sub(r'[^\d.]', '', yes_price_text))
            no_price = int(re.sub(r'[^\d.]', '', no_price_text))

            if yes_price > no_price and yes_price - no_price > 0.03:
                print(f"Buy No: {no_price + 1}\u00A2")
                print(f"Sell Yes: {yes_price - 1}\u00A2")
            elif no_price > yes_price and no_price - yes_price > 0.03:
                print(f"Buy Yes: {yes_price + 1}\u00A2")
                print(f"Sell No: {no_price - 1}\u00A2")
            else:
                print("No arbitrage opportunity")

        assert "No results found." not in driver.page_source
        time.sleep(0.5)

if __name__ == "__main__":
    market_maker()
