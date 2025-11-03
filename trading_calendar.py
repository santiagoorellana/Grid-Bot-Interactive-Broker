'''
Calendario de Trading
Esta es una clase que permite crear un registro de los horarios de apertura y cierre de los mercados 
de interés, sus zonas horarias y excepciones como son navidad, y otros días feriados.
Los datos de los mercados deben declararse dentro de la constante "TRADING_SESSIONS" siguiendo
como ejemplo los mercados que ya estan contenidos en la estructura.
Para conocer si el mercado está abierto se emplea el método "market_open()".
'''

import datetime
import pytz
import logging

TRADING_SESSIONS = {
    "regular": {
        "DEFAULT_SCHEDULE": {
            "market": "NYMEX",
            "weekDayOpen": 0,
            "weekDayClose": 5,
            "hourOpen": 18,
            "hourClose": 17,
            "timeZone": "America/New_York",
            "exceptions": {
                "thanksgivingThursday": {"dateTimeBegin": "2023-11-23 00:00", "dateTimeEnd": "2023-11-23 23:59", "closed": True, "note":"Thanksgiving thursday"},
                "thanksgivingFriday": {"dateTimeBegin": "2023-11-24 00:00", "dateTimeEnd": "2023-11-24 23:59", "closed": True, "note":"Thanksgiving friday"},
                "christmasEve": {"dateTimeBegin": "2023-12-24 00:00", "dateTimeEnd": "2023-11-24 23:59", "closed": True, "note":"Christmas eve"},
                "christmas": {"dateTimeBegin": "2023-12-25 00:00", "dateTimeEnd": "2023-11-24 23:59", "closed": True, "note":"Christmas"}
            }
        },
        "NYMEX": {
            "market": "NYMEX",
            "weekDayOpen": 0,
            "weekDayClose": 5,
            "hourOpen": 6,
            "hourClose": 7,
            "timeZone": "America/New_York",
            "exceptions": {
                "thanksgivingThursday": {"dateTimeBegin": "2023-11-23 00:00", "dateTimeEnd": "2023-11-23 23:59", "closed": True, "note":"Thanksgiving thursday"},
                "thanksgivingFriday": {"dateTimeBegin": "2023-11-24 00:00", "dateTimeEnd": "2023-11-24 23:59", "closed": True, "note":"Thanksgiving friday"},
                "christmasEve": {"dateTimeBegin": "2023-12-24 00:00", "dateTimeEnd": "2023-11-24 23:59", "closed": True, "note":"Christmas eve"},
                "christmas": {"dateTimeBegin": "2023-12-25 00:00", "dateTimeEnd": "2023-11-24 23:59", "closed": True, "note":"Christmas"}
            }
        },
        "NYSE": {
            "market": "NYSE",
            "weekDayOpen": 1,
            "weekDayClose": 5,
            "hourOpen": 4,
            "hourClose": 20,
            "timeZone": "America/New_York",
            "exceptions": {
            }
        }        
    },
    # Esta parte no se esta utilizando ahora, pero servira para excepciones que afecten a todos los mercados.
    # En caso de no ser util, lo podemos quitar simplemente.
    "general_exceptions": {
        "newYear": {"dateTimeBegin": "2024-01-01 00:00", "dateTimeEnd": "2023-11-24 23:59", "closed": True, "note":"New Year"},
        "NASDAQ_christmas": {"dateTimeBegin": "2023-11-24 00:00", "dateTimeEnd": "2023-11-24 23:59", "closed": True, "note":""}
    }
}


class TradingCalendar():

    def __init__(self, localTimeZone, debugMode=False):
        self.tradingSessions = TRADING_SESSIONS
        self.localTimeZone = localTimeZone
        self.debugMode = debugMode
        self.log = logging.getLogger('grid')


    def market_open(self, market, dateTime, verbose=True):
        '''Devuelve True si el mercado especificado está abierto en el momento especificado.'''
        if market not in self.tradingSessions['regular']:
            market = 'DEFAULT_SCHEDULE'
            msg = f"There is no session data for the {market} market. A default schedule will be used."
            if verbose: print(msg)
            self.log.info(msg)
        marketSession = self.tradingSessions['regular'][market]                             # They obtain the session data of the specified market.
        dateTimeUTC = self._to_utc(dateTime, self.localTimeZone)                            # Converts the datetime to UTC.
        dateTimeOnMarketTimeZone = self._to_local(dateTimeUTC, marketSession['timeZone'])   # Converts it to the local date and time of the specified market.
        # Check exceptions first
        for marketSessionKey in marketSession['exceptions'].keys():
            exceptionRange = marketSession['exceptions'][marketSessionKey]
            timeZone = marketSession['timeZone']
            begin = self._localized(datetime.datetime.strptime(exceptionRange['dateTimeBegin'], "%Y-%m-%d %H:%M"), timeZone)
            end = self._localized(datetime.datetime.strptime(exceptionRange['dateTimeEnd'], "%Y-%m-%d %H:%M"), timeZone)
            if dateTimeOnMarketTimeZone >= begin and dateTimeOnMarketTimeZone <= end:
                if exceptionRange['closed']:
                    msg = f"The market {market} is exceptionally closed: {exceptionRange['note']}"
                    if verbose: print(msg)
                    self.log.info(msg)
                    return False
                else:
                    msg = f"The market {market} is exceptionally open: {exceptionRange['note']}"
                    if verbose: print(msg)
                    self.log.info(msg)
                    return True
        weekDay = dateTimeOnMarketTimeZone.weekday()     # Gets the current day of the week in the specified market.
        hour = dateTimeOnMarketTimeZone.hour             # Gets the current time in the specified market.
        # Check the day of the week
        if weekDay < int(marketSession['weekDayOpen']) or weekDay > int(marketSession['weekDayClose']):
            msg = f'The market {market} is not open on {weekDay}.'
            if verbose: print(msg)
            self.log.info(msg)
            return False
        # Check the time
        if hour < marketSession['hourOpen'] or hour >= marketSession['hourClose']:
            msg = f'The market {market} is not open at local hour {hour}.'
            if verbose: print(msg)
            self.log.info(msg)
            return False        
        return True
    
    
    def _to_local(self, dateTime, localTimeZone):
        if self.debugMode: print('dateTime:', dateTime.strftime('%Y-%m-%d %H:%M:%S %Z%z'))
        onLocalTimeZone = dateTime.astimezone(pytz.timezone(localTimeZone))
        if self.debugMode: print('dateTimeOnLocalTimeZone:', onLocalTimeZone.strftime('%Y-%m-%d %H:%M:%S %Z%z'))
        return onLocalTimeZone
        

    def _localized(self, dateTime, localTimeZone):   #"America/New_York"
        '''Convert to datetime object with local timezone.'''
        localTime = pytz.timezone(localTimeZone)
        naiveDateTime = dateTime  #datetime.datetime.strptime(dateTime, "%Y-%m-%d %H:%M:%S")   # Convert to naive datetime object
        localDateTime = localTime.localize(naiveDateTime, is_dst=None)              # Update naive datetime object with local timezone
        return localDateTime
    

    def _to_utc(self, dateTime, localTimeZone): 
        '''Convert datetime object with local timezone to UTC.'''
        localDateTime = self._localized(dateTime, localTimeZone)    # Convert to datetime object with local timezone
        return localDateTime.astimezone(pytz.utc)                   # Convert to UTC


if __name__ == "__main__":
    
    SERVER_LOCATION = "Europe/Berlin"
    
    print('LIST OF ALL TIMEZONES:')
    for tz in pytz.all_timezones: 
        print(tz)
    input('Press any key to continue with test...')
    print('\nTEST LIBRARY:')
    ts = TradingCalendar(SERVER_LOCATION, debugMode=False)
    dt = datetime.datetime.now()
    for n in range(700):
        timeDelta = datetime.timedelta(minutes=30)
        dt = dt + timeDelta
        open = ts.market_open('NYSE', dt, verbose=False)
        print('ServerDateTime:', dt.strftime('%Y-%m-%d %H:%M:%S %Z%z'), ' Open:', open)





