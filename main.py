
from ib_insync import *
from datetime import datetime

from core import Core
import logging
from logging.handlers import TimedRotatingFileHandler
import regex 
import time
import json

# Aquí se ponen todos los parámetros que definen el funcionamiento básico.
CONFIGURATION = {
    'client_tws': 19,
    'tws_ip':"127.0.0.1",
    'tws_port': 7498,
    'reconnection_seconds': 100,        # Tiempo para reintentar reconectar con el API.
    'actualize_status_seconds': 5,      # Actualizacion de la configuracion del google sheets.
    'max_conection_loss_seconds': 15,   # Tiempo maximo que se puede estar sin coneccion para no reiniciar la estrategia.
    'debug_mode': False,                 # Poner en False para que salgan menos lineas en el CMD.

    'google_sheets_document_id': 'TU_GOOGLE_SHEETS_DOCUMENT_ID', 
    'google_sheets_credentials': './credentials.json',
    'dashboard_realtime_level': 0,
    'dashboard_refresh_freq_seconds': 20,    
    
    'telegram_level': 1,
    'telegram_token': 'TOKEN_DEL_BOT_DE_TELEGRAM',
    'telegram_chat_id': 'IDENTIFICADOR_DEL_CHAT_DE_TELEGRAM', 

    'botTimeZone': 'Europe/Berlin',
    'strategy_confirmation_max_age_seconds': 60,
    'relaunch_if_market_closed': False,

    'marquet_data_delayed_but_free': True,  #To obtain free market data, although delayed in time

    "verbose_order_params": False,
    "verbose_risk_data": False,
}

    

def create_logger(name, fileName, filesCount, debugMode):
    '''Prepara la configuracion del logging para guardar mensajes en fichero.'''
    LOG_FORMAT = '%(asctime)s %(levelname)s %(module)s:%(funcName)s:%(lineno)04d - %(message)s'
    handler = TimedRotatingFileHandler(fileName, when="midnight", backupCount=filesCount) 
    handler.setLevel(logging.DEBUG if debugMode else logging.INFO)
    formatter = logging.Formatter(LOG_FORMAT)
    handler.setFormatter(formatter)
    handler.suffix = "%Y%m%d"       # Este es el sufijo del nombre de ficehro.
    handler.extMatch = regex.compile(r"^\d{8}$")   
    log = logging.getLogger(name)
    logging.root.setLevel(logging.NOTSET)
    log.addHandler(handler)
    return log


def _connect_to_broker():
    ''' Intenta conectarse al broker y solo sale de la funcion cuando se logra. '''
    global log
    global core
    global configurationBase
    core.disconnect()
    currentReconnect = 1
    while True:
        print('Trying to connect...')
        log.info('Trying to connect...')
        conection_loss_seconds = time.time() - core.lastConnectionTime
        try:
            core.connect(
                configurationBase['tws_ip'], 
                port=configurationBase['tws_port'], 
                clientId=configurationBase['client_tws'], 
                timeout=5
            )
        except Exception as e:
            text = f'Unabled to connect on attempt {currentReconnect}. Next attempt at {configurationBase["reconnection_seconds"]} seconds.'
            print(text)
            log.exception(f"{text} Exception: {str(e)}")
            currentReconnect += 1
            core.sleep(configurationBase['reconnection_seconds'])        
            continue
        try:
            text = 'CONNECTED! Has been able to connect.'
            print('{} {}'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), text))
            log.info(text)
            core.lastConnectionTime = time.time()
            if conection_loss_seconds > configurationBase['max_conection_loss_seconds']:  
                core.reset_strategies(core.lastDateTimeConnection, True)
            break
        except Exception as e:            
            text = f'Error after connecting on attempt {currentReconnect}. Next attempt at {configurationBase["reconnection_seconds"]} seconds.'
            print(text)
            log.exception(f"{text} Exception: {str(e)}")
            currentReconnect += 1
            core.sleep(configurationBase['reconnection_seconds'])        
            continue
    

def _onDisconnected():
    global log
    '''Si se desconecta el Grid Bot Multiple, lo informa y vuelve a intentar la conexion.'''
    text = 'DISCONNECTED! Connection has been lost...'
    print('{} {}'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), text))
    log.critical(text)
    core.sleep(configurationBase['reconnection_seconds'])
    _connect_to_broker()       # Intenta reconectar.

    
def _onMessageCode(reqId, errorCode, errorString, contract):
    '''Pone en el log los errores que reporta el TWS por su API.'''
    global log
    if int(errorCode) in [1102, 2104, 2158, 2106]:
        log.info('code {}: {}'.format(errorCode, errorString))
    elif int(errorCode) in range(2100, 2170):
        log.warning('code {}: {}'.format(errorCode, errorString))
    else:
        log.error('code {}: {}'.format(errorCode, errorString))


def update_configuration(configFilePath):
    ''' Loads a configuration file given in the parameter config_file_path'''
    global log
    global configurationBase
    try:
        with open(configFilePath, 'r') as file:
            configData = json.load(file)
        configurationBase.update(configData)    # Merge the loaded JSON with the existing global configuration
        text = f'Global configuration updated successfully from: "{configFilePath}"'
        print(text)
        log.error(text)
    except FileNotFoundError:
        text = f'The configuration file does not exist: {configFilePath}'
        print(text)   
        log.error(text)         
    except Exception as e:
        text = f'Error updating configuration file: {e}'
        print(text)   
        log.error(text) 


# Crea el objeto Grid Bot Multiple que ejecuta multiples estrategias a la vez.
configurationBase = CONFIGURATION
log = create_logger('grid', './logs/grid_multiple.log', 7, configurationBase['debug_mode'])
print('{} INITIATED! Grid Bot Multiple has been created'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
log.info('INITIATED! Grid Bot Multiple has been created')
update_configuration("config.json") 
core = Core(configurationBase)        
util.patchAsyncio()
_connect_to_broker()
lastDateTimeBeat = core.read_heart_beat(True)
core.load_strategies_list()
core.reset_strategies(lastDateTimeBeat, False)  
core.disconnectedEvent += _onDisconnected
core.errorEvent += _onMessageCode
core.execDetailsEvent += core.onExecDetailsEvent
core.set_refresh_dashboard()
core.set_actualize_bot_status()
core.run() 


