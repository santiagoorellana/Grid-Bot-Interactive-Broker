
'''
Multi Parámetros

Crea un objeto para manejar los parametros de funcionamiento del bot.
Esta clase es una abstrapción para evitar que el bot baneje directamente el almacanamiento de 
datos que es una hoja de Google Sheet pero a futuro será posible cambiarlo por una database.
Tiene métodos que facilitan el filtrado de los parámetros.

Creado: 17-09-2023
'''
__version__ = '1.0'

from google_sheets_interface import GoogleSheetsInterface
from ib_insync import *
import logging
import time
from real_time_utils import request_historical


class MultiParameters():
    
    def __init__(self, configuration, page=None, beginColumn=1, beginRow=1, columns=2, rows=300):
        '''
        Crea un objeto para manejar los parametros de funcionamiento del bot.
        Esta clase es una abstrapción para evitar que el bot maneje directamente 
        el almacanamiento de datos, además que facilita el filtrado de los parámetros.
        '''
        self.configuration = configuration
        self.multiTable = GoogleSheetsInterface(
            self.configuration['google_sheets_credentials'], 
            self.configuration['google_sheets_document_id']
        )
        self.page = page
        self.beginColumn = beginColumn
        self.beginRow = beginRow
        self.columns = columns
        self.rows = rows
        self.strategies = []
        self.noFilteredStrategies = []
        self.log = logging.getLogger('grid')
        

    def reset(self):
        '''
        Elimina el historial de las estrategias, lo cual hace que todas 
        las estrategias activas se etiqueten como NEW.
        '''
        self.strategies = []


    def load(self, ib, verbose=False):
        '''
        Carga los parámetros desde el almacenamiento y devuelve      
        True: Si se pudieron leer los parámetros desde el almacenamiento.
        False: Si ocurrieron errores durante la lectura de los parámetros. 
        '''
        timeBegin = time.time()
        if verbose:
            print('\nReading strategies from the configuration...')
        tables = self.multiTable.read_tables(self.page, self.beginColumn, self.beginRow, self.columns, self.rows, verbose=verbose)
        if tables is not None:
            tables = self._add_contract_parameters(ib, tables)
            tables = self._add_prices(ib, tables)
            self.noFilteredStrategies = tables
            tables = self._process_and_filter_strategy_params(tables)
            tables = self._add_action_parameter(tables, self.strategies)
            deletedList = self._create_deleted_list(tables, self.strategies)
            tables.extend(deletedList)
            self.strategies = tables
            if verbose:
                for strategy in self.strategies:
                    print('   Strategy: {} Action: {}'.format(strategy['strategyId'], strategy['action']))
                print('   Reading time:', round(time.time()-timeBegin, 2), 'seconds')
        else:
            if verbose: 
                print('Error reading strategies!')


    def _add_prices(self, ib, tables):
        '''Update instruments prices'''
        if ib is None:
            temporalIb = IB()          
            temporalIb.connect("127.0.0.1", port=7497, clientId=999, timeout=5)
        result = []
        delayedButFree = self.configuration['marquet_data_delayed_but_free']
        for strategy in tables:
            try:
                strategy['market'] = None
                if strategy['contract'] is not None:
                    if ib is None:
                        strategy['market'] = request_historical(temporalIb, self.log, strategy['contract'], free=delayedButFree)
                    else:
                        strategy['market'] = request_historical(ib, self.log, strategy['contract'], free=delayedButFree) 
                    if self.configuration['debug_mode']:
                        print(f'contract: {strategy["symbol"]}({strategy["contractId"]})  price: {strategy["market"].close}')
            except Exception as e:
                strategy['market'] = None
                msg = f'Error obtaining price of contract: {strategy["symbol"]}({strategy["contractId"]}) Error: {str(e)}'
                print(msg)
                self.log.exception(msg)
            result.append(strategy)
        if ib is None:
            temporalIb.disconnect()
        return result


    def get_strategy(self, strategyId):
        '''Devuelve la estrategia indicada mediante Id o devuelve None si no existe'''
        try:
            return list(filter(lambda x: int(x['strategyId']) == int(strategyId), self.strategies))[0]
        except:
            return None    


    def _add_contract_parameters(self, ib, newStrategiesList):
        '''Devuelve la lista de estrategias, pero con los parametros contract y contractId establecidos.'''
        result = []
        for strategy in newStrategiesList:
            contract = self._create_contract_parameters(strategy, verbose=True)
            strategy['contract'] = contract
            strategy['contractId'] = ib.get_contract_id(contract)
            result.append(strategy)
        return result


    def _add_action_parameter(self, newStrategiesList, previousStrategiesList):
        '''Devuelve la lista de las estrategias con el parámetro action establecido.'''
        result = []
        for newStrategy in newStrategiesList:
            previousStrategy = list(filter(   # Busca el estado anterior de la estrategia.
                lambda x: x['strategyId'] == newStrategy['strategyId'], 
                previousStrategiesList
            ))
            previousStrategy = previousStrategy[0] if len(previousStrategy) > 0 else None
            strategy = self._set_strategy_action(newStrategy, previousStrategy)
            if strategy is not None:
                result.append(strategy)
        return result


    def _create_deleted_list(self, newStrategiesList, previousStrategiesList):
        '''Devuelve la lista de las estrategias eliminadas con el parametro action establecido.'''
        result = []
        for previousStrategy in previousStrategiesList:
            if previousStrategy['action'] != 'DELETED':
                newStrategy = list(filter(   # Busca el estado actual de la estrategia.
                    lambda x: x['strategyId'] == previousStrategy['strategyId'], 
                    newStrategiesList
                ))
                if len(newStrategy) == 0:
                    strategy = self._set_strategy_action(None, previousStrategy)
                    if strategy is not None:
                        result.append(strategy)
        return result


    def _set_strategy_action(self, newStrategyParam, previousStrategyParam):
        '''
        Agrega el parámetro action a la configuracion de una estrategia.
        Compara los parámetros actuales de la estrategia con los parámetros anteriores.
        
        newStrategyParam: Es el objeto con los nuevos parámetros de de la estrategia.
        previousStrategyParam: Contiene los parámetros anteriores de de la estrategia.
        return: 
        Devuelve la configuración nueva de la estrategia con el parámetro
        action establecido a uno de los siguiente valores:
            NEW = La configuración es de una estrategia nueva que se ha agregado.
            STOP = La configuración indica que se debe detener la estrategia.
            START = La configuración indica que se debe lanzar la estrategia.
            CONTINUE = La configuración indica que la estrategia debe continuar.
            DELETED = Indica que se debe eliminar la estrategia.
        Devuelve None si no se debe agregar la estrategia.
        Si previousStrategyParam es None, se devuelve la estrategia newStrategyParam 
        con el parametro "action" igual a "NEW", solo si el parametro "active" es True.
        De lo contrario devuelve None.
        '''
        if previousStrategyParam is None and newStrategyParam is None:
            return None
        if previousStrategyParam is None:
            newStrategyParam['action'] = 'NEW'
            return newStrategyParam if newStrategyParam['active'] else None
        elif newStrategyParam is None:
            previousStrategyParam['action'] = 'DELETED'
            return previousStrategyParam
        else:
            if previousStrategyParam['active'] and not newStrategyParam['active']:
                newStrategyParam['action'] = 'STOP'
                return newStrategyParam
            elif not previousStrategyParam['active'] and newStrategyParam['active']:
                newStrategyParam['action'] = 'START'
                return newStrategyParam
            else:
                # Importante: Si no hay cambios en el parametro 'active' se deben 
                # mantener los mismos datos que ya estan en el bot aunque ya existan 
                # datos nuevos puestos por el usuario en el FrontEnd.
                previousStrategyParam['action'] = 'CONTINUE'
                return previousStrategyParam


    def _create_contract_parameters(self, strategyParams, verbose=False):
        '''Crea el parametro contract (Stock, Future) que se necesita para lanzar las ordenes.'''
        if strategyParams is None or strategyParams == {}: return None
        try:
            if strategyParams['symbol'] is None: return None
            if strategyParams['exchange'] is None: return None
            if strategyParams['currency'] is None: return None
            if strategyParams['mode'] == 'FUTURE':
                return Future(
                    symbol = strategyParams['symbol'], 
                    lastTradeDateOrContractMonth = strategyParams['futureLastDate'], 
                    exchange = strategyParams['exchange'], 
                    localSymbol = strategyParams['futureLocalSymbol'], 
                    multiplier = strategyParams['futureMultiplier'],
                    currency = strategyParams['currency']
                )
            elif strategyParams['mode'] == 'STOCK':
                return Stock(
                    strategyParams['symbol'],
                    strategyParams['exchange'],
                    strategyParams['currency'] 
                )
            else:
                return None
        except Exception as e:
            msg = f'Error creating contract object: {str(e)}'
            if verbose: print(msg)
            self.log.exception(msg)
            return None
        

    def _process_strategy_params(self, strategy, debugMode=False):
        '''
        Transforma los parametros de la estrategia y los convierte al tipo de datos que se necesita.
        strategy: Es un diccionario con los parametros de la estrategia.
        return: Retorna la misma strategy pero con los tipos de datos 
                establecidos segun la necesidad del algoritmo del Bot.
				Si ocurre un error procesando la estrategia, devuelve None.
        '''
        if strategy is None or strategy == {}:
            if debugMode:
                self.log.error('La estrategia no puede ser un valor None.')
            return None

        if strategy['strategyId'] is None:
            if debugMode:
                self.log.error('The strategy identifier is missing.')
            return None
        if strategy['strategyType'] is None:
            if debugMode:
                self.log.error('The type of strategy is missing.')
            return None
        prefix = 'En la estrategia {}'.format(strategy['strategyId'])
        try:
            # Intenta convertir los valores al tipo de dato requerido.
            strategy['active'] = self.multiTable.is_active(strategy['active'])
            if not strategy['active']: 
                return None
            
            strategy['outsideRth'] = self.multiTable.str_to_boolean(strategy['outsideRth'])
            
            # Intenta convertir los valores al tipo de dato requerido.
            strategy['strategyId'] = int(strategy['strategyId'])
            strategy['initialPrice'] = self.multiTable.string_to_float(strategy['initialPrice'])
            strategy['orderQty'] = int(strategy['orderQty'])
            strategy['step'] = self.multiTable.string_to_float(strategy['step'])
            strategy['buyOrders'] = int(strategy['buyOrders'])
            strategy['sellOrders'] = int(strategy['sellOrders'])
            strategy['maxLongRisk'] = float(strategy['maxLongRisk'])
            strategy['maxShortRisk'] = float(strategy['maxShortRisk'])            
            
            #These may not be established
            try:
                strategy['refPrice'] = self.multiTable.string_to_float(strategy['refPrice']) 
            except:
                pass
            try:
                strategy['orderAuxPrice'] = self.multiTable.string_to_float(strategy['orderAuxPrice']) if strategy['orderAuxPrice'] != '' else ''
            except:
                pass
            try:
                strategy['activeBuyOrders'] = int(strategy['activeBuyOrders']) if strategy['activeBuyOrders'] != '' else ''
            except:
                pass
            try:
                strategy['activeSellOrders'] = int(strategy['activeSellOrders']) if strategy['activeSellOrders'] != '' else ''
            except:
                pass
            try:
                strategy['stopStep'] = self.multiTable.string_to_float(strategy['stopStep']) if strategy['stopStep'] != '' else ''
            except:
                pass
            try:
                strategy['closeStep'] = self.multiTable.string_to_float(strategy['closeStep']) if strategy['closeStep'] != '' else ''
            except:
                pass
            try:
                strategy['displaySize'] = int(strategy['displaySize']) if strategy['displaySize'] != '' else ''
            except:
                pass

            # Verifica que los valores numericos esten en los rangos aceptables.
            if strategy['initialPrice'] < 0: 
                if debugMode:
                    self.log.error('{}, el parámetro "initialPrice" no puede ser negativo.'.format(prefix))
                return None
            if strategy['orderQty'] < 0: 
                if debugMode:
                    self.log.error('{}, el parámetro "orderQty" no puede ser negativo.'.format(prefix))
                return None
            if strategy['step'] < 0: 
                if debugMode:
                    self.log.error('{} el parámetro "step" no puede ser negativo.'.format(prefix))
                return None
            if strategy['buyOrders'] < 0: 
                if debugMode:
                    self.log.error('{} el parámetro "buyOrders" no puede ser negativo.'.format(prefix))
                return None
            if strategy['sellOrders'] < 0: 
                if debugMode:
                    self.log.error('{} el parámetro "sellOrders" no puede ser negativo.'.format(prefix))
                return None
            if strategy['maxLongRisk'] < 0: 
                if debugMode:
                    self.log.error('{} el parámetro "maxLongRisk" no puede ser negativo.'.format(prefix))
                return None
            if strategy['maxShortRisk'] < 0: 
                if debugMode:
                    self.log.error('{} el parámetro "maxShortRisk" no puede ser negativo.'.format(prefix))
                return None

            # Comprueba si existen los parametros comunes
            if strategy['mode'] is None: 
                if debugMode:
                    self.log.error('{} falta el valor del parámetro "mode"'.format(prefix))
                return None
            if strategy['symbol'] is None: 
                if debugMode:
                    self.log.error('{} falta el valor del parámetro "symbol"'.format(prefix))
                return None
            if strategy['exchange'] is None: 
                if debugMode:
                    self.log.error('{} falta el valor del parámetro "exchange"'.format(prefix))
                return None
            if strategy['currency'] is None: 
                if debugMode:
                    self.log.error('{} falta el valor del parámetro "currency"'.format(prefix))
                return None

            # Comprueba si existen los parametros del modo FUTURE
            if strategy['mode'] == 'FUTURE':
                if strategy['futureLastDate'] is None: 
                    if debugMode:
                        self.log.error('{} falta el valor del parámetro "futureLastDate"'.format(prefix))
                    return None
                if strategy['futureLocalSymbol'] is None: 
                    if debugMode:
                        self.log.error('{} falta el valor del parámetro "futureLocalSymbol"'.format(prefix))
                    return None
                if strategy['futureMultiplier'] is None: 
                    if debugMode:
                        self.log.error('{} falta el valor del parámetro "futureMultiplier"'.format(prefix))
                    return None   
            return strategy
        except Exception as e:
            if debugMode:
                self.log.exception('{}, ocurrio un error leyendo los parámetros...'.format(prefix))
            return None


    def _process_and_filter_strategy_params(self, strategies):
        '''
        Transforma los parametros de la lista al tipo de datos que se necesita.

        parameters: Es un array que contiene las tablas leidas.
        return: Retorna la misma lista de tablas (parametros) pero con los tipos
                de datos establecidos segun la necesidad del algoritmo del Bot.
        '''
        result = []
        for strategy in strategies:
            strategyTyped = self._process_strategy_params(strategy, False)
            if strategyTyped is not None:
                result.append(strategyTyped)
            else:
                #self.log.error('No se pudo agregar la estrategia: {}'.format(strategy))
                pass
        return result



def test():
    '''Muestra como utilizar la librería y permite probarla.'''
    print('Presione Ctrl+C si desea abortar la prueba')
    print('Haga los cambios en la hoja Google Sheet y los verá aquí:')
    parameters = MultiParameters()
    while True:
        parameters.load(True)
        time.sleep(5)

#test()
