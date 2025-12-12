"""
Fair Value Service

Computes theoretical fair values for weather markets using NWS forecast data.
Maps temperature probability distributions to YES/NO contract prices.
"""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import requests

logger = logging.getLogger(__name__)


# NWS Forecast Office for NYC (New York, NY)
NYC_FORECAST_OFFICE = "OKX"  # Upton, NY covers NYC
NYC_GRID_X = 33
NYC_GRID_Y = 37


@dataclass
class TemperatureForecast:
    """Temperature forecast for a specific time."""
    valid_time: datetime
    temperature_f: float
    probability_of_precipitation: Optional[float] = None


@dataclass
class FairValueResult:
    """Result of fair value calculation."""
    ticker: str
    fair_value: float  # 0-100 (cents)
    confidence: float  # 0-1
    forecast_temp: Optional[float] = None
    threshold_temp: Optional[float] = None
    market_type: Optional[str] = None  # 'above', 'below', 'between'
    reasoning: Optional[str] = None


class WeatherService:
    """
    Fetches weather forecasts from the National Weather Service API.
    
    NWS API is free and doesn't require authentication.
    Docs: https://www.weather.gov/documentation/services-web-api
    """
    
    def __init__(self):
        self._cache: Dict[str, Tuple[datetime, Any]] = {}
        self._cache_duration = timedelta(minutes=15)
    
    def get_forecast(
        self,
        office: str = NYC_FORECAST_OFFICE,
        grid_x: int = NYC_GRID_X,
        grid_y: int = NYC_GRID_Y
    ) -> Optional[List[TemperatureForecast]]:
        """
        Get hourly temperature forecast.
        
        Returns list of TemperatureForecast objects for the next ~7 days.
        """
        cache_key = f"{office}_{grid_x}_{grid_y}"
        
        # Check cache
        if cache_key in self._cache:
            cached_time, cached_data = self._cache[cache_key]
            if datetime.now(timezone.utc) - cached_time < self._cache_duration:
                return cached_data
        
        try:
            # NWS gridpoints endpoint for hourly forecast
            url = f"https://api.weather.gov/gridpoints/{office}/{grid_x},{grid_y}/forecast/hourly"
            
            headers = {
                "User-Agent": "KalshiMarketMaker/1.0 (weather-trading-bot)",
                "Accept": "application/geo+json"
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"NWS API error: {response.status_code}")
                return None
            
            data = response.json()
            periods = data.get("properties", {}).get("periods", [])
            
            forecasts = []
            for period in periods:
                # Parse the time
                start_time = period.get("startTime")
                if start_time:
                    dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                else:
                    continue
                
                temp = period.get("temperature")
                if temp is None:
                    continue
                
                # Convert to Fahrenheit if needed
                temp_unit = period.get("temperatureUnit", "F")
                if temp_unit == "C":
                    temp = temp * 9/5 + 32
                
                forecasts.append(TemperatureForecast(
                    valid_time=dt,
                    temperature_f=float(temp),
                    probability_of_precipitation=period.get("probabilityOfPrecipitation", {}).get("value")
                ))
            
            # Cache the result
            self._cache[cache_key] = (datetime.now(timezone.utc), forecasts)
            
            logger.info(f"Fetched {len(forecasts)} hourly forecasts from NWS")
            return forecasts
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch NWS forecast: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing NWS forecast: {e}")
            return None
    
    def get_high_temp_forecast(
        self,
        target_date: datetime
    ) -> Optional[Tuple[float, float]]:
        """
        Get forecasted high temperature for a specific date.
        
        Returns:
            Tuple of (forecasted_high, confidence) or None
        """
        forecasts = self.get_forecast()
        if not forecasts:
            return None
        
        # Filter to target date (in local time)
        target_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        target_end = target_start + timedelta(days=1)
        
        day_forecasts = [
            f for f in forecasts
            if target_start <= f.valid_time.replace(tzinfo=None) < target_end
        ]
        
        if not day_forecasts:
            # Try without timezone
            day_forecasts = [
                f for f in forecasts
                if target_start.date() == f.valid_time.date()
            ]
        
        if not day_forecasts:
            logger.warning(f"No forecasts found for {target_date.date()}")
            return None
        
        # Find the max temperature
        high_temp = max(f.temperature_f for f in day_forecasts)
        
        # Confidence decreases with forecast distance
        hours_out = (target_date - datetime.now(timezone.utc)).total_seconds() / 3600
        
        if hours_out < 24:
            confidence = 0.9
        elif hours_out < 48:
            confidence = 0.8
        elif hours_out < 72:
            confidence = 0.7
        else:
            confidence = 0.5
        
        return (high_temp, confidence)


class FairValueCalculator:
    """
    Calculates fair values for Kalshi temperature markets.
    
    Market ticker format: KXHIGHNY-YYMMMDD-<TYPE><TEMP>
    Types:
        - T<temp>: Above threshold (e.g., T50 = "above 50°")
        - B<temp>: Between range (e.g., B46.5 = "46-47°")
        - (implicit): Below threshold (e.g., just the temp means below)
    """
    
    def __init__(self):
        self._weather = WeatherService()
        # Standard deviation of forecast error (degrees F)
        # Increases with forecast distance
        self._base_std_dev = 2.0
    
    def parse_ticker(self, ticker: str) -> Optional[Dict]:
        """
        Parse a market ticker to extract date and temperature threshold.
        
        Returns dict with:
            - date: datetime of the settlement date
            - threshold: temperature threshold
            - market_type: 'above', 'below', or 'between'
            - range_low/range_high: for 'between' type
        """
        # Pattern: KXHIGHNY-YYMMMDD-<TYPE><TEMP>
        # Examples:
        #   KXHIGHNY-25DEC10-T47 (above 47°)
        #   KXHIGHNY-25DEC10-T40 (above 40° - but title says "below")
        #   KXHIGHNY-25DEC10-B46.5 (between 46-47°)
        
        pattern = r"KXHIGHNY-(\d{2})([A-Z]{3})(\d{2})-([TB])?([\d.]+)"
        match = re.match(pattern, ticker)
        
        if not match:
            logger.warning(f"Could not parse ticker: {ticker}")
            return None
        
        year = 2000 + int(match.group(1))
        month_str = match.group(2)
        day = int(match.group(3))
        type_char = match.group(4)  # T, B, or None
        temp = float(match.group(5))
        
        # Parse month
        months = {
            'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4,
            'MAY': 5, 'JUN': 6, 'JUL': 7, 'AUG': 8,
            'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
        }
        month = months.get(month_str)
        if not month:
            return None
        
        try:
            date = datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            return None
        
        result = {
            'date': date,
            'threshold': temp,
        }
        
        if type_char == 'T':
            result['market_type'] = 'above'
        elif type_char == 'B':
            result['market_type'] = 'between'
            # For "between" markets, threshold is the midpoint
            # Range is typically 2 degrees (e.g., B46.5 = 46-47°)
            result['range_low'] = int(temp)
            result['range_high'] = int(temp) + 1
        else:
            result['market_type'] = 'below'
        
        return result
    
    def calculate_fair_value(
        self,
        ticker: str,
        market_title: Optional[str] = None
    ) -> Optional[FairValueResult]:
        """
        Calculate fair value for a market.
        
        Uses weather forecast + normal distribution to estimate probability.
        """
        parsed = self.parse_ticker(ticker)
        if not parsed:
            return None
        
        # Get forecast
        forecast_result = self._weather.get_high_temp_forecast(parsed['date'])
        if not forecast_result:
            return FairValueResult(
                ticker=ticker,
                fair_value=50.0,  # Default to 50/50
                confidence=0.0,
                reasoning="No forecast available"
            )
        
        forecast_temp, base_confidence = forecast_result
        
        # Calculate probability based on market type
        threshold = parsed['threshold']
        market_type = parsed['market_type']
        
        # Adjust for market title if available (sometimes ticker parsing is ambiguous)
        if market_title:
            if '<' in market_title or 'below' in market_title.lower():
                market_type = 'below'
            elif '>' in market_title or 'above' in market_title.lower():
                market_type = 'above'
        
        # Standard deviation increases with forecast distance
        hours_out = (parsed['date'] - datetime.now(timezone.utc)).total_seconds() / 3600
        std_dev = self._base_std_dev * (1 + hours_out / 48)  # Increase by 1x every 2 days
        
        # Use normal distribution CDF for probability
        from math import erf, sqrt
        
        def normal_cdf(x, mu, sigma):
            """Cumulative distribution function of normal distribution."""
            return 0.5 * (1 + erf((x - mu) / (sigma * sqrt(2))))
        
        if market_type == 'above':
            # P(temp > threshold)
            probability = 1 - normal_cdf(threshold, forecast_temp, std_dev)
        elif market_type == 'below':
            # P(temp < threshold)
            probability = normal_cdf(threshold, forecast_temp, std_dev)
        elif market_type == 'between':
            # P(range_low <= temp < range_high)
            low = parsed.get('range_low', threshold - 0.5)
            high = parsed.get('range_high', threshold + 0.5)
            probability = normal_cdf(high, forecast_temp, std_dev) - normal_cdf(low, forecast_temp, std_dev)
        else:
            probability = 0.5
        
        # Convert to fair value in cents (1-99)
        fair_value = max(1, min(99, round(probability * 100)))
        
        return FairValueResult(
            ticker=ticker,
            fair_value=fair_value,
            confidence=base_confidence,
            forecast_temp=forecast_temp,
            threshold_temp=threshold,
            market_type=market_type,
            reasoning=f"Forecast: {forecast_temp:.1f}°F, Threshold: {threshold}°F, P={probability:.2%}"
        )
    
    def calculate_all_fair_values(
        self,
        markets: List[Dict]
    ) -> Dict[str, FairValueResult]:
        """Calculate fair values for a list of markets."""
        results = {}
        
        for market in markets:
            ticker = market.get('ticker')
            title = market.get('title')
            
            if ticker:
                fv = self.calculate_fair_value(ticker, title)
                if fv:
                    results[ticker] = fv
        
        return results


# Global instances
weather_service = WeatherService()
fair_value_calculator = FairValueCalculator()
