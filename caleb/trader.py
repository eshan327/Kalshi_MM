#limit order autobalancer
class Trader:

    def __init__(self, market):
        self.market = market
        self.yes_asks_limits = []
        self.yes_bids_limits = []
        self.no_asks_limits = []
        self.no_bids_limits = []
    #four prices for our target market -> what we should do
    def trade(self, yes_ask, no_ask, yes_bid, no_bid): 
        if yes_ask + no_ask < 100:
            print("market order both")
            return
        
        if yes_bid + no_bid < 99:
            print("place bids for both and also check if we can sell it")
            self.yes_bids_limits.append(yes_bid + 1)
            self.no_bids_limits.append(no_bid + 1)

        print("balance out for bid ask spread")
        while len(self.yes_bids_limits) > len(self.yes_asks_limits):
            self.yes_asks_limits.append(yes_ask - 1)
        
        while len(self.no_bids_limits) > len(self.no_asks_limits):
            self.no_asks_limits.append(no_ask - 1)

    
    #a fulfilled order -> the order we must perform to balance it
    def fulfillOrder(self, type):
        if type == "yes ask":
            self.yes.asks_bids.pop()
        elif type == "no ask":
            self.yes_asks_limits.pop()
        elif type == "yes bid":
            self.no_bids_limits.pop()
        elif type == "no bid":
            self.no_bids_limits.pop()
        balancelength = min(len(self.no_asks_limits), len(self.no_bids_limits),len(self.yes_asks_limits), len(self.yes_bids_limits))
        while len( self.yes_asks_limits) > balancelength:
            print("cancel yes bid")
            self.yes.asks_limits.pop()

        while len(self.yes_asks_limits) > balancelength:    
            print("cancel yes ask")
            self.yes_asks_limit.pop()
        while len(self.no_bids_limits) > balancelength:
            print("cancel no bid")
            self.no_bids_limit.pop()
        while len(self.no_bids_limits) > balancelength:    
            print("cancel no ask")
            self.no_bids_limit.pop()
    
    
