from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
import configparser

def market_maker():

    # Loading config.ini
    config = configparser.ConfigParser()
    try:
        config.read('config.ini')
        username = config['Credentials']['username']
        password = config['Credentials']['password']
        max_position = int(config['Trading']['max_position'])
        max_capital = int(config['Trading']['max_capital'])
    except:
        print("Error loading config.ini.")
        return
    
    driver = webdriver.Firefox()
    
    # Signing in first
    driver.get("https://kalshi.com/sign-in")
    print("Signing in...")
    time.sleep(5)
    
    try:
        username_field = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='email']"))
        )
        password_field = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='password']"))
        )
        
        username_field.clear()
        username_field.send_keys(username)
        password_field.clear()
        password_field.send_keys(password)
        
        login_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.button-0-1-19.fullWidth-0-1-21.medium-0-1-24.brand-0-1-39[type='submit']"))
        )
        driver.execute_script("arguments[0].click();", login_button)
        
        # 2FA
        time.sleep(3)
        current_url = driver.current_url
        
        if "two-factor-code" in current_url:
            print("2FA required. Input the code.")
            
            max_wait = 120  # Waits up to 2 minutes for code
            start_time = time.time()
            
            while "two-factor-code" in driver.current_url:
                if time.time() - start_time > max_wait:
                    print("Timed out waiting for 2FA")
                    driver.quit()
                    return
                time.sleep(2)
                
            print("2FA complete.")
        
        WebDriverWait(driver, 30).until(
            EC.any_of(
                EC.url_contains("/markets"),
                EC.url_contains("kalshi.com/"),
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'userMenuContainer')]"))
            )
        )
        print("Login successful")
        
    except Exception as e:
        print(f"Login failed: {e}")
        driver.quit()
        return
    
    # Now move to the NYC page
    driver.get("https://kalshi.com/markets/kxhighny/highest-temperature-in-nyc")
    time.sleep(5)

    tile_group = driver.find_element(By.CLASS_NAME, 'tileGroup-0-1-124')
    while True:
        markets = tile_group.find_elements(By.XPATH, "*")[0:3]
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

if __name__ == "__main__":
    market_maker()
