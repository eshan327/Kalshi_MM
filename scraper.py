from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
import time
import re

def market_maker():
    driver = webdriver.Firefox()
    driver.get("https://kalshi.com/markets/kxhighny/highest-temperature-in-nyc")
    time.sleep(5)

    tile_group = driver.find_element(By.CLASS_NAME, 'tileGroup-0-1-124')
    while True:
        markets = tile_group.find_elements(By.XPATH, "*")
        markets = markets[0:3]
        for market in markets:
            label = market.find_element(By.CLASS_NAME, 'flex').get_attribute("innerHTML")
            market.click()

            # yes prices
            try:
                headingContainer = market.find_elements(By.CLASS_NAME, 'headingContainer-0-1-230')[0]
            except:
                headingContainer = market.find_elements(By.CLASS_NAME, 'headingContainer-0-1-232')[0]
            yes_button = headingContainer.find_elements(By.TAG_NAME, 'button')[0]
            driver.execute_script("arguments[0].click();", yes_button)

            yes_orderbook = market.find_element(By.CLASS_NAME, 'orderbookContent-0-1-280')
            yes_prices_raw = yes_orderbook.find_elements(By.CLASS_NAME, 'orderBookItem-0-1-286')
            yes_prices = []
            for price in yes_prices_raw:
                spans = price.find_elements(By.TAG_NAME, 'span')
                if len(spans) == 5:
                    yes_prices.append(int(re.sub(r'[^\d.]', '', spans[2].text)))
            yes_ask_price = yes_prices[0]
            yes_bid_price = yes_prices[1]

            print(f"\n{label}")
            print("Contract: Yes")
            print(f"Ask Price: {yes_ask_price}")
            print(f"Bid Price: {yes_bid_price}")
            if yes_ask_price - yes_bid_price >= 3:
                print(f"Bid at {yes_bid_price + 1}\u00A2, Ask at {yes_ask_price - 1}\u00A2")
                print(f"Profit: {yes_ask_price - yes_bid_price - 2}\u00A2")

                # root_container = driver.find_element(By.CLASS_NAME, 'eventPageContent-0-1-91')
                # order_container = root_container.find_element(By.XPATH, '//div[@data-sentry-component="PublicOrderPanel"]')
                # buy_button = order_container.find_elements(By.CLASS_NAME, 'underlineText-0-1-265')[1]
                # driver.execute_script("arguments[0].click();", buy_button)
                # time.sleep(5)

            else:
                print("No market making opportunity")

            # no prices
            try:
                headingContainer = market.find_elements(By.CLASS_NAME, 'headingContainer-0-1-230')[0]
            except:
                headingContainer = market.find_elements(By.CLASS_NAME, 'headingContainer-0-1-232')[0]
            no_button = headingContainer.find_elements(By.TAG_NAME, 'button')[1]
            driver.execute_script("arguments[0].click();", no_button)

            no_orderbook = driver.find_element(By.CLASS_NAME, 'orderbookContent-0-1-280')
            no_prices_raw = no_orderbook.find_elements(By.CLASS_NAME, 'orderBookItem-0-1-286')
            no_prices = []
            for price in no_prices_raw:
                spans = price.find_elements(By.TAG_NAME, 'span')
                if len(spans) == 5:
                    no_prices.append(int(re.sub(r'[^\d.]', '', spans[2].text)))
            no_ask_price = no_prices[0]
            no_bid_price = no_prices[1]

            print(f"\n{label}")
            print("Contract: No")
            print(f"Ask Price: {no_ask_price}")
            print(f"Bid Price: {no_bid_price}")
            if no_ask_price - no_bid_price >= 3:
                print(f"Bid at {no_bid_price + 1}\u00A2, Ask at {no_ask_price - 1}\u00A2")
                print(f"Profit: {no_ask_price - no_bid_price - 2}\u00A2")
            else:
                print("No market making opportunity")

            assert "No results found." not in driver.page_source
            time.sleep(0.5)

if __name__ == "__main__":
    market_maker()
