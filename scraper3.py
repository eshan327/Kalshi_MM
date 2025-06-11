from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
import random
import datetime
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import signal
import sys
import os
import configparser

class TradingSimulator:
    def __init__(self, initial_balance=1000):
        self.balance = initial_balance
        self.positions = {}  # {contract_id_type: {"qty": qty, "price": price, "type": "yes/no"}}
        self.trade_history = []  # [(timestamp, balance, action, profit)]
        self.balance_history = [(datetime.datetime.now(), initial_balance)]
        self.next_sell_time = self.generate_next_sell_time()
        self.max_open_positions = 3
        self.sell_on_next_iteration = False
        self.forced_trade_indices = []
        self.order_tracker = OrderTracker()

         # New methods to handle order tracking
    
    def place_order_on_kalshi(self, logged_driver, label, yes_no, buy_sell, price, qty):
        """Place an order on Kalshi but don't update simulator yet"""
        # Check position limits before attempting to place buy orders
        if buy_sell == 0:  # Buy order
            current_open_positions = self.get_total_open_contracts()
            pending_buy_orders = sum(1 for order in self.order_tracker.pending_orders if order.buy_sell == 0)
            total_potential_positions = current_open_positions + pending_buy_orders
            
            if total_potential_positions >= self.max_open_positions:
                print(f"Position limit reached ({self.max_open_positions}). Open: {current_open_positions}, Pending buys: {pending_buy_orders}")
                return None
    
        order = place_order(logged_driver, label, yes_no, buy_sell, price, qty)
        if order:
            self.order_tracker.add_pending_order(order)
        return order
    
    def process_filled_orders(self, logged_driver):
        """Check for filled orders and update simulator state"""
        filled_orders = self.order_tracker.check_fills(logged_driver)
        for filled_order in filled_orders:
            # Generate a unique contract ID based on order details
            contract_id = f"kalshi_{filled_order.label.replace(' ', '_')}_{int(time.time())}"
            
            if filled_order.buy_sell == 0:  # Buy order
                contract_type = "yes" if filled_order.yes_no == 0 else "no"
                self.buy_contract(contract_id, contract_type, filled_order.price)
                print(f"Updated simulator: Bought {contract_type} contract for {filled_order.label}")
            else:  # Sell order
                # Find matching position to sell
                position_to_sell = None
                for pos_key, pos_data in self.positions.items():
                    pos_type = "yes" if filled_order.yes_no == 0 else "no"
                    if pos_data["type"] == pos_type:
                        position_to_sell = pos_key
                        break
                
                if position_to_sell:
                    self.sell_contract(position_to_sell, filled_order.price)
                    print(f"Updated simulator: Sold {pos_type} contract for {filled_order.label}")
                    self.sell_on_next_iteration = False
                else:
                    print(f"Warning: No matching position found to sell for {filled_order.label}")

    def generate_next_sell_time(self):
        seconds = random.uniform(10, 15)
        return datetime.datetime.now() + datetime.timedelta(seconds=seconds)
    
    def get_total_open_contracts(self):
        return sum(position["qty"] for position in self.positions.values())
    
    def buy_contract(self, contract_id, contract_type, price):
        if self.get_total_open_contracts() >= self.max_open_positions:
            print(f"Position limit reached ({self.max_open_positions})")
            return False
        
        position_key = f"{contract_id}_{contract_type}"
        qty = 1
        cost = qty * price / 100.0
        
        if cost > self.balance:
            print(f"Not enough cash to buy {price}¢")
            return False
        
        self.balance -= cost
        
        if position_key in self.positions:
            current_qty = self.positions[position_key]["qty"]
            current_price = self.positions[position_key]["price"]
            total_qty = current_qty + qty
            avg_price = (current_qty * current_price + qty * price) / total_qty
            self.positions[position_key]["qty"] = total_qty
            self.positions[position_key]["price"] = avg_price
        else:
            self.positions[position_key] = {"qty": qty, "price": price, "type": contract_type}
        
        now = datetime.datetime.now()
        self.trade_history.append((now, self.balance, "BUY", 0))
        self.balance_history.append((now, self.balance))
        
        print(f"Bought {qty} {contract_type} contract at {price}¢")
        print(f"Balance: ${self.balance:.2f} | Positions: {self.get_total_open_contracts()}/{self.max_open_positions}")
        return True
    
    def sell_contract(self, position_key, price):
        if position_key not in self.positions:
            print(f"Position {position_key} not found")
            return False
        
        position = self.positions[position_key]
        qty = position["qty"]
        buy_price = position["price"]
        contract_type = position["type"]
        
        sell_amount = qty * price / 100.0
        cost_basis = qty * buy_price / 100.0
        profit = sell_amount - cost_basis
        
        self.balance += sell_amount
        del self.positions[position_key]
        
        now = datetime.datetime.now()
        self.trade_history.append((now, self.balance, "SELL", profit))
        self.balance_history.append((now, self.balance))
        
        contract_id = position_key.split('_')[0]
        print(f"Sold {qty} {contract_type} contract at {price}¢ (bought at {buy_price}¢)")
        print(f"Profit: ${profit:.2f} | Balance: ${self.balance:.2f}")
        
        return True
    
    def check_for_sells(self, markets_data):
        now = datetime.datetime.now()
        
        if now >= self.next_sell_time:
            print("\n----- Time to sell -----")
            if self.positions:
                self.sell_on_next_iteration = True
                print("Will sell next profitable position encountered")
            else:
                print("No open positions")
            
            self.next_sell_time = self.generate_next_sell_time()
            minutes = (self.next_sell_time - now).total_seconds() / 60.0
            print(f"Next sell: {self.next_sell_time.strftime('%H:%M:%S')} (in {minutes:.1f} min)")
            print("-----------------------\n")
    
    def sell_all_positions(self, markets_data):
        if not self.positions:
            return
            
        print("\n----- Selling positions in this bet -----")
        for position_key in list(self.positions.keys()):
            parts = position_key.split('_')
            if len(parts) < 2:
                continue
                
            contract_id, contract_type = parts[0], parts[1]
            price = None
            
            for market_info in markets_data:
                if market_info["id"] == contract_id:
                    if contract_type == "yes" and "yes_bid_price" in market_info:
                        price = market_info["yes_bid_price"]
                    elif contract_type == "no" and "no_bid_price" in market_info:
                        price = market_info["no_bid_price"]
                    break
            
            if not price:
                price = self.positions[position_key]["price"]
                print(f"No market data for {position_key}; using original price")
            
            self.forced_trade_indices.append(len(self.balance_history))
            self.sell_contract(position_key, price)
            
        print("-----------------------------\n")
    
    def plot_balance_history(self):
        if not self.balance_history:
            return
            
        os.makedirs("plots", exist_ok=True)
        times, balances = zip(*self.balance_history)
        
        plt.figure(figsize=(10, 6))
        
        for i in range(1, len(times)):
            is_forced = i in self.forced_trade_indices
            if is_forced:
                plt.plot([times[i-1], times[i]], [balances[i-1], balances[i]], 
                         marker='o', linestyle=':', color='red', alpha=0.7)
            else:
                plt.plot([times[i-1], times[i]], [balances[i-1], balances[i]], 
                         marker='o', linestyle='-', color='blue')
        
        plt.title('Account Balance')
        plt.xlabel('Time')
        plt.ylabel('Balance ($)')
        plt.grid(True)
        
        legend_elements = [
            Line2D([0], [0], color='blue', lw=2, marker='o', label='Normal Trading'),
            Line2D([0], [0], color='red', lw=2, linestyle=':', marker='o', label='Liquidation')
        ]
        plt.legend(handles=legend_elements, loc='upper left')
        
        initial_balance = self.balance_history[0][1]
        final_balance = balances[-1]
        profit = final_balance - initial_balance
        percent_return = (profit / initial_balance) * 100
        
        plt.annotate(f'P/L: ${profit:.2f} ({percent_return:.2f}%)',
                     xy=(0.02, 0.95), xycoords='axes fraction',
                     fontsize=10, bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.8))
        
        plt.gcf().autofmt_xdate()
        plt.tight_layout()
        plt.savefig('plots/trading_balance_history.png')
        plt.close()
        print("Balance history saved to 'plots/trading_balance_history.png'")

    def plot_profit_history(self):
        if not self.trade_history:
            return
            
        os.makedirs("plots", exist_ok=True)
        
        sell_times = [self.balance_history[0][0]]
        profits = [0]
        cumulative_profit = 0
        
        for timestamp, _, action, profit in self.trade_history:
            if action == "SELL":
                cumulative_profit += profit
                sell_times.append(timestamp)
                profits.append(cumulative_profit)
        
        if len(sell_times) <= 1:
            return
        
        plt.figure(figsize=(10, 6))
        
        plt.plot(sell_times, profits, marker='o', linestyle='-', color='blue')
        
        plt.title('Profit/Loss')
        plt.xlabel('Time')
        plt.ylabel('Profit/Loss ($)')
        plt.grid(True)
        
        plt.axhline(y=0, color='k', linestyle='-', alpha=0.3)
        
        final_profit = profits[-1]
        initial_balance = self.balance_history[0][1]
        percent_return = (final_profit / initial_balance) * 100
        
        plt.annotate(f'P/L: ${final_profit:.2f} ({percent_return:.2f}%)',
                     xy=(0.02, 0.95), xycoords='axes fraction',
                     fontsize=10, bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.8))
        
        plt.gcf().autofmt_xdate()
        plt.tight_layout()
        plt.savefig('plots/trading_profit_history.png')
        plt.close()
        print("Profit history saved to 'plots/trading_profit_history.png'")

    def generate_trade_summary(self):
        print("\n----- TRADING SUMMARY -----")
        print(f"Starting balance: ${self.balance_history[0][1]:.2f}")
        print(f"Final balance: ${self.balance:.2f}")
        
        profit = self.balance - self.balance_history[0][1]
        percent_return = (profit / self.balance_history[0][1]) * 100
        print(f"Total P/L: ${profit:.2f} ({percent_return:.2f}%)")
        
        buy_count = sum(1 for _, _, action, _ in self.trade_history if action == "BUY")
        
        regular_sells = [i for i, (_, _, action, _) in enumerate(self.trade_history) 
                        if action == "SELL" and i not in self.forced_trade_indices]
        forced_sells = [i for i, (_, _, action, _) in enumerate(self.trade_history) 
                    if action == "SELL" and i in self.forced_trade_indices]
        
        regular_count = len(regular_sells)
        forced_count = len(forced_sells)
        
        print(f"Buy trades: {buy_count}")
        print(f"Regular sells: {regular_count}")
        print(f"Forced sells: {forced_count}")
        
        # Add order tracking statistics
        print(f"Total orders placed: {self.order_tracker.total_orders_placed}")
        print(f"Total orders filled: {self.order_tracker.total_orders_filled}")
        print(f"Orders fill rate: {(self.order_tracker.total_orders_filled/self.order_tracker.total_orders_placed)*100:.2f}%" if self.order_tracker.total_orders_placed > 0 else "N/A")
        
        if regular_count > 0:
            profitable = sum(1 for i, (_, _, action, profit) in enumerate(self.trade_history) 
                        if action == "SELL" and profit > 0 and i not in self.forced_trade_indices)
            
            print(f"Win rate: {(profitable/regular_count)*100:.2f}%")
            
            profits = [p for i, (_, _, action, p) in enumerate(self.trade_history) 
                    if action == "SELL" and p > 0 and i not in self.forced_trade_indices]
            losses = [p for i, (_, _, action, p) in enumerate(self.trade_history) 
                    if action == "SELL" and p <= 0 and i not in self.forced_trade_indices]
            
            if profits:
                print(f"Avg win: ${sum(profits)/len(profits):.2f}")
            
            if losses:
                print(f"Avg loss: ${sum(losses)/len(losses):.2f}")
        
        print("---------------------------\n")

def market_maker(logged_driver, market_url):
    
    simulator = TradingSimulator(initial_balance=1000)
    markets_data = []
    
    def signal_handler(sig, frame):
        print("\nExiting...")
        if markets_data:
            simulator.sell_all_positions(markets_data)
        
        simulator.generate_trade_summary()
        simulator.plot_balance_history()
        simulator.plot_profit_history()
        
        try:
            driver.quit()
        except:
            pass
        
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    driver = webdriver.Firefox()
    driver.get(market_url)
    # time.sleep(5)
    
    print("\n----- TRADING SIMULATION -----")
    print(f"Strategy: Buy up to {simulator.max_open_positions} contracts where spread ≥ 3¢")
    # print(f"Selling one contract every 30-90 seconds to simulate Kalshi's liquidity and volume")
    print("-----------------------------\n")
    
    start_time = datetime.datetime.now()
    
    try:
        # tile_group = driver.find_element(By.CLASS_NAME, 'tileGroup-0-1-124')
        tile_group = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[class^='tileGroup']"))
        )
        while True:
            simulator.process_filled_orders(logged_driver)

            # Get current position count after processing fills
            current_positions = simulator.get_total_open_contracts()
            pending_buys = sum(1 for order in simulator.order_tracker.pending_orders if order.buy_sell == 0)
            
            print(f"\nCurrent positions: {current_positions}/{simulator.max_open_positions}, Pending buys: {pending_buys}")
            
            # Skip market scanning if we're at or over position limit
            # if current_positions + pending_buys >= simulator.max_open_positions:
            #     print("At position limit, skipping market scan")
            #     time.sleep(5)
            #     continue

            markets = tile_group.find_elements(By.XPATH, "*")
            markets = markets[0:3]
            markets_data = []
            
            for market in markets:
                try:
                    contract_id = f"temp_{len(markets_data)}"
                    market_data = {"id": contract_id}
                    
                    label = market.find_element(By.CLASS_NAME, 'flex').get_attribute("innerHTML")
                    market.click()
    
                    # yes prices
                    headingContainer = market.find_element(By.CSS_SELECTOR, "[class^='headingContainer']")
                    yes_button = headingContainer.find_elements(By.TAG_NAME, 'button')[0]
                    driver.execute_script("arguments[0].click();", yes_button)
    
                    yes_orderbook = market.find_element(By.CSS_SELECTOR, "[class^='orderbookContent']")
                    yes_prices_raw = yes_orderbook.find_elements(By.CSS_SELECTOR, "[class^='orderBookItem']")
                    yes_prices = []
                    for price in yes_prices_raw:
                        spans = price.find_elements(By.TAG_NAME, 'span')
                        if len(spans) == 5:
                            yes_prices.append(int(re.sub(r'[^\d.]', '', spans[2].text)))
                    
                    if len(yes_prices) >= 2:
                        yes_ask_price = yes_prices[0]
                        yes_bid_price = yes_prices[1]
                        
                        market_data["yes_ask_price"] = yes_ask_price
                        market_data["yes_bid_price"] = yes_bid_price
    
                        print(f"\n{label}")
                        print("Contract: Yes")
                        print(f"Ask Price: {yes_ask_price}")
                        print(f"Bid Price: {yes_bid_price}")
                        
                        position_key = f"{contract_id}_yes"
                        if simulator.sell_on_next_iteration and position_key in simulator.positions:
                            buy_price = simulator.positions[position_key]["price"]
                            qty = simulator.positions[position_key]["qty"]
                            sell_price = yes_ask_price - 1
                            print(f"Selling {qty} at {sell_price}¢ (bought at {buy_price}¢)")

                            simulator.place_order_on_kalshi(logged_driver, label, yes_no=0, buy_sell=1, price=sell_price, qty=qty)
                                
                            # simulator.sell_contract(position_key, sell_price)
                            # simulator.sell_on_next_iteration = False
                        elif yes_ask_price - yes_bid_price >= 3:
                            print(f"Bid at {yes_bid_price + 1}\u00A2, Ask at {yes_ask_price - 1}\u00A2")
                            print(f"Profit: {yes_ask_price - yes_bid_price - 2}\u00A2")
                            current_positions = simulator.get_total_open_contracts()
                            pending_buys = sum(1 for order in simulator.order_tracker.pending_orders if order.buy_sell == 0)
                            if current_positions + pending_buys < simulator.max_open_positions:

                                simulator.place_order_on_kalshi(logged_driver, label, yes_no=0, buy_sell=0, price=yes_bid_price + 1, qty=1)
                            else:
                                print(f"Skipping buy: position limit reached ({current_positions} positions, {pending_buys} pending buys)")
                        else:
                            print("No market making opportunity")
                    else:
                        print(f"\n{label}")
                        print("Contract: Yes - Insufficient data")
    
                    # no prices
                    headingContainer = market.find_element(By.CSS_SELECTOR, "[class^='headingContainer']")
                    no_button = headingContainer.find_elements(By.TAG_NAME, 'button')[1]
                    driver.execute_script("arguments[0].click();", no_button)
    
                    no_orderbook = market.find_element(By.CSS_SELECTOR, "[class^='orderbookContent']")
                    no_prices_raw = no_orderbook.find_elements(By.CSS_SELECTOR, "[class^='orderBookItem']")
                    no_prices = []
                    for price in no_prices_raw:
                        spans = price.find_elements(By.TAG_NAME, 'span')
                        if len(spans) == 5:
                            no_prices.append(int(re.sub(r'[^\d.]', '', spans[2].text)))
                    
                    if len(no_prices) >= 2:
                        no_ask_price = no_prices[0]
                        no_bid_price = no_prices[1]
                        
                        market_data["no_ask_price"] = no_ask_price
                        market_data["no_bid_price"] = no_bid_price
    
                        print(f"\n{label}")
                        print("Contract: No")
                        print(f"Ask Price: {no_ask_price}")
                        print(f"Bid Price: {no_bid_price}")
                        
                        position_key = f"{contract_id}_no"
                        if simulator.sell_on_next_iteration and position_key in simulator.positions:
                            buy_price = simulator.positions[position_key]["price"]
                            qty = simulator.positions[position_key]["qty"]
                            sell_price = no_ask_price - 1
                            print(f"Selling {qty} at {sell_price}¢ (bought at {buy_price}¢)")

                            simulator.place_order_on_kalshi(logged_driver, label, yes_no=1, buy_sell=1, price=sell_price, qty=qty)
                            
                            # simulator.sell_contract(position_key, sell_price)
                            # simulator.sell_on_next_iteration = False
                        elif no_ask_price - no_bid_price >= 3:
                            print(f"Bid at {no_bid_price + 1}\u00A2, Ask at {no_ask_price - 1}\u00A2")
                            print(f"Profit: {no_ask_price - no_bid_price - 2}\u00A2")

                            current_positions = simulator.get_total_open_contracts()
                            pending_buys = sum(1 for order in simulator.order_tracker.pending_orders if order.buy_sell == 0)
                            if current_positions + pending_buys < simulator.max_open_positions:
                                sell_price = no_ask_price + 1
                                simulator.place_order_on_kalshi(logged_driver, label, yes_no=1, buy_sell=0, price=no_bid_price + 1, qty=1)
                            else:
                                print(f"Skipping buy: position limit reached ({current_positions} positions, {pending_buys} pending buys)")
                        else:
                            print("No market making opportunity")
                    else:
                        print(f"\n{label}")
                        print("Contract: No - Insufficient data")
                    
                    markets_data.append(market_data)
                    
                except Exception as e:
                    print(f"Error: {e}")
                    continue
                    
                assert "No results found." not in driver.page_source
            
            simulator.check_for_sells(markets_data)
            # time.sleep(3)
            
            if (datetime.datetime.now() - start_time).total_seconds() > 1800:
                print("\nReached 30 minute limit")
                simulator.sell_all_positions(markets_data)
                break
    
    except Exception as e:
        print(f"Error: {e}")
        if markets_data:
            simulator.sell_all_positions(markets_data)
    
    finally:
        end_time = datetime.datetime.now()
        print(f"\nEnded at {end_time}")
        print(f"Duration: {end_time - start_time}")
        
        simulator.generate_trade_summary()
        simulator.plot_balance_history()
        simulator.plot_profit_history()
        
        try:
            driver.quit()
        except:
            pass

class Order:
    def __init__(self, label, yes_no, buy_sell, price, qty, order_id=None):
        self.label = label
        self.yes_no = yes_no  # 0 for Yes, 1 for No
        self.buy_sell = buy_sell  # 0 for Buy, 1 for Sell
        self.price = price
        self.qty = qty
        self.timestamp = datetime.datetime.now()
        self.order_id = order_id  # Unique ID from Kalshi if available
        self.filled = False
        self.fill_timestamp = None
    
    def __str__(self):
        contract_type = "Yes" if self.yes_no == 0 else "No"
        action = "Buy" if self.buy_sell == 0 else "Sell"
        status = "Filled" if self.filled else "Pending"
        return f"{self.label} - {contract_type} - {action} - {self.price}¢ - {self.qty} contracts - {status}"
    
    def mark_as_filled(self):
        self.filled = True
        self.fill_timestamp = datetime.datetime.now()
        
def place_order(order_driver, label, yes_no, buy_sell, price, qty, wait_time=5):
    order = Order(label, yes_no, buy_sell, price, qty)
    
    try:
        # print("Finding market group based on label...")
        temp_group = order_driver.find_element(By.XPATH, f'//*[contains(text(), "{label}")]/ancestor::*[5]')
        # print("Market group found.")
        yes_no_button = temp_group.find_elements(By.CSS_SELECTOR, "[class^='pill']")[yes_no]
        order_driver.execute_script("arguments[0].click();", yes_no_button)

        # print("Locating Buy/Sell container...")
        if buy_sell == 0:  
            buy_sell_button = order_driver.find_element(By.XPATH, '//button[.//span[text()="Buy"]]')
        else:
            buy_sell_button = order_driver.find_element(By.XPATH, '//button[.//span[text()="Sell"]]')
        order_driver.execute_script("arguments[0].click();", buy_sell_button)
        # print("Buy/Sell option selected.")

        # print("Locating input container...")
        contracts_label = order_driver.find_element(By.XPATH, '//span[contains(text(), "Contracts")]')
        input_container = contracts_label.find_element(By.XPATH, './ancestor::div[3]')
        contract_input = input_container.find_elements(By.TAG_NAME, 'input')[0]
        contract_input.clear()
        contract_input.send_keys(qty)
        # print("Quantity input entered.")

        limit_input = input_container.find_elements(By.TAG_NAME, 'input')[1]
        limit_input.clear()
        limit_input.send_keys(price)
        # print("Price input entered.")

        # print("Clicking review order button...")
        review_button = input_container.find_elements(By.TAG_NAME, 'button')[0]
        order_driver.execute_script("arguments[0].click();", review_button)
        # print("Review order clicked.")

        print("Clicking confirm button...")
        submit_label = order_driver.find_element(By.XPATH, '//span[contains(text(), "Submit")]')
        submit_container = submit_label.find_element(By.XPATH, './ancestor::div[1]')
        submit_button = submit_container.find_elements(By.TAG_NAME, 'button')[0]
        order_driver.execute_script("arguments[0].click();", submit_button)
        print("Order confirmed.")

        print(f"Order placed on Kalshi: {order}")
        time.sleep(wait_time)
        return order

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Failed to place order on Kalshi: {e}")
        return None
    
class OrderTracker:
    def __init__(self):
        self.pending_orders = []
        self.filled_orders = []
        self.total_orders_placed = 0
        self.total_orders_filled = 0
        self.order_history = []  # Track all orders for debugging
    
    def add_pending_order(self, order):
        if order is not None:
            self.pending_orders.append(order)
            self.total_orders_placed += 1
            self.order_history.append((datetime.datetime.now(), "PLACED", order))
            print(f"Added pending order: {order}")
            print(f"Total orders placed: {self.total_orders_placed}, Filled: {self.total_orders_filled}, Pending: {len(self.pending_orders)}")
    
    def check_fills(self, logged_driver):
        """Check which orders have been filled using orders tab"""
        print("Checking for order fills...")
        filled_orders = []
        
        tile_group = WebDriverWait(logged_driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[class^='tileGroup']"))
        )
        
        markets = tile_group.find_elements(By.XPATH, "*")
        markets = markets[0:3]
        
        for market in markets:
            temp_label = market.find_element(By.CLASS_NAME, 'flex').get_attribute("innerHTML") 
            order_label = market.find_elements(By.TAG_NAME, 'span')[1].get_attribute("innerHTML") 
            if "Yes ·" in order_label or "No ·" in order_label:
                parts = order_label.split("·")
                if len(parts) > 1:
                    number_part = parts[1].strip().split(" ")[0]
                    current_owned = int(number_part)
                    
                    print(f"Current owned: {current_owned} for {temp_label}")
                    for pending_order in self.pending_orders[:]: 
                        if pending_order.label == temp_label:
                            if not hasattr(pending_order, 'previous_owned'):
                                pending_order.previous_owned = 0
                            if current_owned != pending_order.previous_owned:
                                if current_owned > pending_order.previous_owned and pending_order.buy_sell == 0:
                                    self.pending_orders.remove(pending_order)
                                    pending_order.mark_as_filled()
                                    self.filled_orders.append(pending_order)
                                    self.total_orders_filled += 1
                                    print(f"Buy order confirmed filled: {pending_order}")
                                    filled_orders.append(pending_order)
                                elif current_owned < pending_order.previous_owned and pending_order.is_buy == 1:
                                    self.pending_orders.remove(pending_order)
                                    pending_order.mark_as_filled()
                                    self.filled_orders.append(pending_order)
                                    self.total_orders_filled += 1
                                    print(f"Sell order confirmed filled: {pending_order}")
                                    filled_orders.append(pending_order)
                                
                            pending_order.previous_owned = current_owned
            else:
                current_owned = 0
                temp_label = market.find_element(By.CLASS_NAME, 'flex').get_attribute("innerHTML") 
                print(f"Current owned: {current_owned} for {temp_label}")
                for pending_order in self.pending_orders[:]:
                    if pending_order.label == temp_label:
                        if not hasattr(pending_order, 'previous_owned'):
                            pending_order.previous_owned = 0
                        if current_owned != pending_order.previous_owned:
                            if pending_order.previous_owned > 0 and not pending_order.is_buy:
                                self.pending_orders.remove(pending_order)
                                pending_order.mark_as_filled()
                                self.filled_orders.append(pending_order)
                                self.total_orders_filled += 1
                                print(f"Sell order confirmed filled: {pending_order}")
                                filled_orders.append(pending_order)
                        
                        pending_order.previous_owned = current_owned
        
        return filled_orders
        
def login(driver):
    config = configparser.ConfigParser()
    try:
        config.read('config.ini')
        username = config['Credentials']['username']
        password = config['Credentials']['password']
        max_position = int(config['Trading']['max_position'])
        max_capital = int(config['Trading']['max_capital'])
        market_url = config['Trading']['url']
    except Exception as e:
        print(f"Error loading config.ini: {e}")
        raise

    print("Signing in...")
    driver.get("https://kalshi.com/sign-in")
    
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
            EC.element_to_be_clickable((
                By.CSS_SELECTOR, "button[class^='button'][class*='fullWidth'][class*='medium'][class*='brand'][type='submit']"
            ))
        )
        driver.execute_script("arguments[0].click();", login_button)
        time.sleep(1)
        current_url = driver.current_url
        
        if "two-factor-code" in current_url:
            print("2FA required. Input the code.")
            
            max_wait = 120 
            start_time = time.time()
            
            while "two-factor-code" in driver.current_url:
                if time.time() - start_time > max_wait:
                    print("Timed out waiting for 2FA")
                    driver.quit()
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

    driver.get(market_url)
    # time.sleep(2)
    return market_url

def setup_orders_window(driver):
    """Create a new tab in the existing driver to monitor orders"""
    try:
        login(driver)
        driver.get("https://kalshi.com/account/activity")
        # container = driver.find_element(By.CLASS_NAME, 'pills-0-1-156')
        # orders_tab = container.find_elements(By.TAG_NAME, 'button')[4]
        # driver.execute_script("arguments[0].click();", orders_tab)
        print("Created order monitoring tab")
        # time.sleep(3) 
        
    except Exception as e:
        print(f"Error creating orders tab: {e}")
        orders_window = None

if __name__ == "__main__":
    driver = webdriver.Firefox()
    market_url = login(driver)
    # time.sleep(1)
    dollars_button = WebDriverWait(driver, 5).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "[class^='interactiveHeader']")))[0]
    driver.execute_script("arguments[0].click();", dollars_button)
    container = driver.find_element(By.CSS_SELECTOR, '[style="display: flex; min-width: 200px; padding: 4px 16px;"]')
    limit_button = container.find_elements(By.CSS_SELECTOR, "[class^='row'][class*='interactive']")[2]
    driver.execute_script("arguments[0].click();", limit_button)
    # order_driver = webdriver.Firefox()
    # setup_orders_window(order_driver)
    # time.sleep(1)
    market_maker(driver, market_url)

    order_driver = webdriver.Firefox()
    market_url = login(order_driver)
    time.sleep(1)
    dollars_button = WebDriverWait(order_driver, 5).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "[class^='interactiveHeader']")))[0]
    order_driver.execute_script("arguments[0].click();", dollars_button)
    limit_span = order_driver.find_element(By.XPATH, '//span[contains(text(), "Limit order")]')
    container = limit_span.find_element(By.XPATH, './ancestor::div[5]')
    limit_button = container.find_elements(By.CSS_SELECTOR, "[class^='row'][class*='interactive']")[2]
    order_driver.execute_script("arguments[0].click();", limit_button)
    time.sleep(2)
    market_maker(order_driver, market_url)