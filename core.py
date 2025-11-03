
'''
Crea un objeto que representa al broker o exchange.
Esta clase extiende las propiedades y metodos de la clase IB de ib_insync.
'''
from ib_insync import *
from order_id_manager import OrderIdManager
from datetime import datetime, timedelta
import ctypes
from multi_parameters import MultiParameters
import time
from risk_manager import RiskManager
from trading_calendar import TradingCalendar
from dashboard import Dashboard
import telegram
import logging


ctypes.windll.kernel32.SetConsoleTitleW(__file__)


class Core(IB):
    def __init__(self, configuration):
        '''
        Crea un objeto que representa al broker o exchange.
        Esta clase es una abstrapción para evitar que el bot baneje directamente 
        los detalles de interaccion con el broker o exchange.
        '''
        IB.__init__(self)
        self.configuration = configuration
        self.orderIdManager = OrderIdManager(self.configuration['client_tws'])
        self.parameters = MultiParameters(self.configuration, 'Estrategias')
        self.dashBoard = Dashboard(self.configuration) 
        self.riskManager = RiskManager(self.configuration)
        self.tradingCalendar = TradingCalendar(configuration['botTimeZone'])
        self.lastTimeOrder = None
        self.lastTimeActualize = time.time()
        self.accumulatedTime = 0
        self.log = logging.getLogger('grid')
        self.lastConnectionTime = time.time()
        self.lastDateTimeConnection = datetime.fromtimestamp(self.lastConnectionTime)
        self.previousConnectedStatus = None
        
    

    def load_strategies_list(self):
        '''Load strategies without executing them.'''
        try:
            if self.isConnected():
                self.parameters.load(self, verbose=False)
                msg = 'Strategies have been loaded'
                print(msg)
                self.log.info(msg)
                telegram.send_to_telegram(msg, self.configuration)   
                return True
            else:
                msg = 'Disconnected!!! Cannot load strategies.'
                print(msg)
                self.log.error(msg)
                telegram.send_to_telegram(msg, self.configuration)   
        except Exception as e:
            self.log.exception('Error: {}'.format(str(e)))            
        return False



    def set_actualize_bot_status(self):
        '''
        Verifica la conexion del bot, actualiza el estado de la configuracion multiparametrica 
        y realiza las acciones indicadas en la configuración de cada estrategia.
        '''
        if 'debug_mode' in self.configuration:
            nowTime = time.time()
            seconds = round(nowTime - self.lastTimeActualize, 2)
            self.lastTimeActualize = nowTime
            labelStatus = 'Connected.' if self.isConnected() else 'Disconnected'
            if not self.configuration['debug_mode'] and seconds <= 30:
                self.accumulatedTime += seconds
                if self.accumulatedTime >= (60 * 60):
                    print(labelStatus, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                    self.accumulatedTime = 0
            else:
                print(labelStatus, 'Seconds since last callback:', seconds)
        try:
            if self.isConnected():
                if self.previousConnectedStatus is not None and self.previousConnectedStatus != self.isConnected():
                    msg = 'Connection with Interactive Brokers reestablished!!!'
                    self.log.info(msg)
                    telegram.send_to_telegram(msg, self.configuration)   
                self.previousConnectedStatus = self.isConnected()

                self.lastDateTimeConnection = datetime.fromtimestamp(self.lastConnectionTime)  # Guarda la copia antes de que sea actualizada.
                self.lastConnectionTime = time.time()   # Registra el tiempo de la ultima conexion comprobada.
                self.parameters.load(self, verbose=False)
                for strategy in self.parameters.strategies:
                    #print('contractId:', self.get_contract_id(strategy))  # Esto lo utilice para probar la funcion get_contract_id
                    
                    # Si el precio es cero, solicitamos el precio al mercado
                    if float(strategy['initialPrice']) == float(0):
                        strategy['initialPrice'] = self.get_price(strategy)
                    
                    if strategy['initialPrice'] is not None:
                        if strategy['action'] == 'NEW' or strategy['action'] == 'START':
                            if strategy['active']:
                                #self.dashBoard.update_dashboard(self, self.parameters)
                                self.dashBoard.update_risk(self.riskManager)
                                msg = 'On contract {}, strategy {} {}'.format(strategy['contractId'], strategy['strategyId'], strategy['action'])
                                print(msg)
                                self.log.info(msg)
                                self.post_grid_orders(strategy)
                        elif strategy['action'] == 'STOP' or strategy['action'] == 'DELETED':
                            msg = 'Estrategia {} {}'.format(strategy['strategyId'], strategy['action'])
                            print(msg)
                            self.log.info(msg)
                            self.cancel_orders_of_strategy(strategy['strategyId'])
                        elif strategy['action'] == 'CONTINUE':
                            # No se reporta nada. Continua trabajando OK
                            pass
                        else:
                            self.log.warn('No se reconoce la accion "{}" de la estrategia {}'.format(strategy['action'], strategy['strategyId']))
                            pass 
                    else:
                        self.log.warn('No se pudo obtener el precio para la estrategia: {}'.format(strategy['strategyId']))
                    self.sleep(0)   # Garantiza el funcionamiento asyncrono
            else:
                if self.previousConnectedStatus != self.isConnected():
                    msg = 'Disconnected from Interactive Brokers!!!'
                    self.log.error(msg)
                    telegram.send_to_telegram(msg, self.configuration)   
                self.previousConnectedStatus = self.isConnected()

            #self.dashBoard.update_dashboard(self, self.parameters)          
            self.dashBoard.update_risk(self.riskManager)
            msg_heartbeat = f"{datetime.now()} -- {__file__} -- Heartbeat"  
            with open("heartbeat.txt", "w") as f: f.write(msg_heartbeat)
        except Exception as e:
            self.log.exception('Error: {}'.format(str(e)))            
        finally:
            self.schedule(
                callback=self.set_actualize_bot_status, 
                time=self.get_timestamp_for_seconds(self.configuration['actualize_status_seconds'])
            ) 
             


    def set_refresh_dashboard(self):
        '''Update the dashboard data.'''
        try:
            self.dashBoard.update_dashboard(self, self.parameters)          
        except Exception as e:
            self.log.exception('Error refreshing the dashboard: {}'.format(str(e)))            
        finally:
            self.schedule(
                callback=self.set_refresh_dashboard, 
                time=self.get_timestamp_for_seconds(self.configuration['dashboard_refresh_freq_seconds'])
            ) 
             


    def get_contract_id(self, contract):
        '''
        Solicitar los detalles del contrato para obtener el conId.
        contract: Objeto de conrato que puede ser Stock, Future, etc
        return: Devuelve el ID del contrato. SI ocurre error, reporta al log y devuelve None.
        '''
        if contract is not None: 
            try:
                self.qualifyContracts(contract)
                return contract.conId
            except Exception as e:
                self.log.exception('No se pudo obtener el ID de contrato para: {}'.format(contract))
                return None
        else:
            return None



    def get_price(self, strategy):
        '''
        Pedimos el precio y cancelamos la suscripción.
        Si no se cancela la suscripción, se produce un error.
        
        '''
        ################################
        # Esto hay que implementarlo.... ###
        ################################
        return None



    def onExecDetailsEvent(self, trade, fill):
        self.dashBoard.load_fill(fill)   #******* OJO ***** esto deberia ejecutarse despues del if (float(trade.remaining()) == 0):
        self.dashBoard.update_risk(self.riskManager)
        try:
            if (float(trade.remaining()) == 0):
                self.riskManager.add_executed_operation(trade, self)
                unpackedOrderId = self.orderIdManager.unpack(int(trade.order.orderRef))
                if unpackedOrderId is not None:
                    strategy = self.parameters.get_strategy(unpackedOrderId['strategyId'])
                
                    if strategy is None: return
                    if not strategy['active']: return
                    if strategy['action'] == 'DELETED': return
                    if strategy['action'] == 'STOP': return
                    
                    msg = 'Executed order {} type {} of strategy {} at price {}'.format(
                        unpackedOrderId['number'], 
                        unpackedOrderId['side'],
                        unpackedOrderId['strategyId'],
                        trade.order.lmtPrice
                    )
                    print('{} - {}'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), msg))
                    self.log.info(msg)
                    telegram.send_to_telegram(msg, self.configuration)

                    if (trade.order.action == "SELL"): 
                        self.post_order(strategy, 'BUY', trade.order.lmtPrice - strategy['step'], prefix=f'strategy {strategy["strategyId"]} Reaction ')                
                    elif (trade.order.action == "BUY"):
                        self.post_order(strategy, 'SELL', trade.order.lmtPrice + strategy['step'], prefix=f'strategy {strategy["strategyId"]} Reaction ')                
                    else:
                        pass
                else:
                    msg = 'Executed unknown order at price {}'.format(trade.order.lmtPrice)
                    print('{} - {}'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), msg))
                    self.log.info(msg)
                    telegram.send_to_telegram(msg, self.configuration)
        except Exception as e:
            text = 'Error poniendo orden contraria al trade'
            self.log.exception('{}: {} {}'.format(text, trade, fill))
            return



    def post_grid_orders(self, strategy, verbose=True):
        '''
        Crea las órdenes de compra y venta que componen la cuadrícula (grid).
        strategy: Esta es la configuración de la estrategia que se va a realizar con el grid.
        initialPrice: Precio central a partir del cual se calculan los niveles de comra y venta del grid.
        return: True si pudo poner las ordenes y False si ocurre algun error.
        '''
        if self.can_post_grid(strategy):
            try:
                print("{} - Insertando ordenes para crear el GRID...".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                print('   Initial price:', strategy['initialPrice'], strategy['currency'])
                initialPrice = strategy['initialPrice']
                # Manuel. 11-10-23. OJO!! en las compras podrían darse precios negativos. Hay que controlarlo.            
                for ordinal in range(1, strategy['buyOrders'] + 1):
                    self.post_order(strategy, 'BUY', initialPrice - (strategy['step'] * ordinal), prefix=f'strategy {strategy["strategyId"]} Initial Low {ordinal} ')
                    self.sleep(0)   # Garantiza el funcionamiento asyncrono
                for ordinal in range(1, strategy['sellOrders'] + 1):
                    self.post_order(strategy, 'SELL', initialPrice + (strategy['step'] * ordinal), prefix=f'strategy {strategy["strategyId"]} Initial Up {ordinal} ')
                    self.sleep(0)   # Garantiza el funcionamiento asyncrono
                self.log.info('Se han creado las ordenes grid de la estrategia {}'.format(strategy['strategyId']))
                return True
            except Exception as e:
                msg = 'Error creating strategy grid orders {}'.format(strategy['strategyId'])
                if verbose: print(msg)
                self.log.exception(msg)
                telegram.send_to_telegram(msg, self.configuration)   
                return False
        else:
            # Ya fue reportado dentro de can_post_grid()
            pass



    def can_post_grid(self, strategy):
        '''Check if the user has confirmed the execution of the strategy.'''
        try:
            rangeMin = float(strategy['initialPrice'] - strategy['step']) if strategy['buyOrders'] == 0 else float(0)
            rangeMax = float(strategy['initialPrice'] + strategy['step']) if strategy['sellOrders'] == 0 else float(9999999999)
            if strategy['market'].close <= rangeMin or strategy['market'].close >= rangeMax:
                if strategy['confirmed'] is None: 
                    msg = 'Canceled strategy {} because there is no confirmation.'.format(strategy['strategyId'])
                    print(msg)
                    self.log.error(msg)
                    telegram.send_to_telegram(msg, self.configuration)   
                    return False
                else:
                    if time.time() - int(strategy['confirmed']) < self.configuration['strategy_confirmation_max_age_seconds']:
                        return True
                    else:
                        msg = 'Canceled strategy {} because the confirmation is expired.'.format(strategy['strategyId'])
                        print(msg)
                        self.log.error(msg)
                        telegram.send_to_telegram(msg, self.configuration)   
                        return False
            else:
                return True
        except Exception as e:
            msg = 'Canceled strategy {} because an error has occurred.'.format(strategy['strategyId'])
            print(msg)
            self.log.exception(msg)
            telegram.send_to_telegram(msg, self.configuration)   
            return False



    def post_order(self, strategy, side, price, verbose=True, prefix=''):
        '''
        Agrega una orden de compra o venta que componen la cuadrícula (grid).
        
        strategy: Esta es la configuración de la estrategia que se va a realizar.
        side: Este es el tipo de operación que se va a realizar BUY o SELL.
        price: Este es el precio en el que se va a poner la orden.
        return: Retorna True si se pudo poner la orden. De lo contrario False.
        '''           
        try:
            orderId = self.orderIdManager.create_id(strategy['contractId'], strategy['strategyId'], side)

            paramOutsideRth = strategy.get('outsideRth', True)
            paramValidity = strategy.get('validity', 'GTC')
            paramOrderType = strategy.get('orderType', 'LMT') 

            order = Order(
                action=side, 
                totalQuantity=strategy['orderQty'], 
                lmtPrice=price, 
                outsideRth = paramOutsideRth if paramOutsideRth is not None else True, 
                tif = paramValidity if paramValidity is not None else 'GTC', 
                orderType = paramOrderType if paramOrderType is not None else 'LMT', 
                orderRef=orderId
            )
            if 'orderAuxPrice' in strategy:
                if strategy['orderAuxPrice'] != None:
                    order.auxPrice = strategy['orderAuxPrice']

            if 'displaySize' in strategy:
                if strategy['displaySize'] != None:
                    if float(strategy['displaySize']) >= float(strategy['orderQty']):
                        self.log.error('Display size {} must by lower than order quantity {}.'.format(strategy['displaySize'], strategy['orderQty']))
                        return False     
                    order.displaySize = strategy['displaySize']
                    order.hidden = strategy['displaySize'] == 0 

            if self.configuration.get("verbose_order_params", False):
                print('-----------ORDER-PARAMS-----------------')
                print('action:', side)
                print('totalQuantity:', strategy['orderQty'])
                print('outsideRth:', paramOutsideRth if paramOutsideRth != '' else True)
                print('tif:', paramValidity if paramValidity != '' else 'GTC')
                print('orderType:', paramOrderType if paramOrderType != '' else 'LMT')
                print('displaySize:', order.displaySize)
                print('hidden:', order.hidden)
                print('auxPrice:', order.auxPrice)
                print('-----------------------------')
                
            if self.validate_order(order, strategy):
                trade = self.placeOrder(strategy['contract'], order)
                self.lastTimeOrder = datetime.now()
                self.sleep(0)   # Garantiza el funcionamiento asyncrono
                msg = f"{prefix}Order: {orderId} {side} {order.totalQuantity} en {trade.contract.symbol} al precio {order.lmtPrice}"
                if verbose: print(f'   {msg}')
                self.log.info(msg)
                telegram.send_to_telegram(msg, self.configuration)
            else:
                if verbose: print('   Riesgo no aceptable. No se insertó la orden {} {} en precio {}'.format(side, strategy['symbol'], price))
        except Exception as e:
            self.log.exception('Error agregando orden {} {} en precio {}'.format(side, strategy['symbol'], price))
            return False



    def validate_order(self, order, strategy, verbose=False):
        '''
        Esta funcion analiza los datos de la orden y el contexto para validar la realización.
        
        strategy: Esta es la configuración de la estrategia que se va a realizar.
        side: Este es el tipo de operación que se va a realizar BUY o SELL.
        price: Este es el precio en el que se va a poner la orden.
        orderId: Este es el identificador con el que se va a poner la orden.
        self: En el parámetro self se va a tener acceso al resto de las funciones de la clase core.
        return: Retorna True para autorizar la realización de la operación o False para no realizarla.
        '''
        timeBegin = time.time()
        operate = self.riskManager.can_operate(order, strategy, self)
        if not operate: 
            text = f'   Order rejected at {round(time.time()-timeBegin, 2)} seconds'
            self.log.info(text)
            if verbose and not operate: 
                print(text)
        return operate



    def cancel_all_orders(self, verbose=True):
        '''
        Cancela las órdenes activas del cliente.
        verbose: Pongase en False para que no se muestren mensajes en consola.
        return: Devuelve True si se ejecuta correctamente. False si ocurre un error. 
        '''
        # Manuel. ¿Esto por qué lo hacemos al principio? No me acuerdo.
        self.dashBoard.update_dashboard(self, self.parameters)
        self.dashBoard.update_risk(self.riskManager)
        try:
            count = 0
            if verbose:
                print('{} - Searching pending orders for all client strategies...'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            # Manuel.  Cambiar por self.reqAllOpenOrders() por si acaso openORders() no descarga las órdenes que no son de este cliente
            # Manuel.  Crear un parámetro global para indicar si se cancela todo o no, incluidas órdenes de otros clientes
            # Manuel.  El valor por defecto del parámetro global es que si, se cancelaría todo
            for order in self.openOrders():
                if self.orderIdManager.is_order_child_of_client(order.orderRef):
                    if verbose:
                        print('   Cancelada orden', order.orderRef)
                    self.cancel_order(order)
                    count += 1
                self.sleep(0)   # Garantiza el funcionamiento asyncrono
            msg = 'Se han cancelado {} órdenes pendientes de todas las estrategias del cliente'.format(count)
            if verbose:
                print(f'   {msg}')
            self.log.info(msg)
            return True
        except Exception as e:
            self.log.exception('Error cancelando ordenes')
            return False



    def cancel_orders_of_strategy(self, strategyId, verbose=True):
        '''
        Cancela las órdenes activas de una estrategia especifica.
        strategyId: Número identificador de la estrategia que se debe cancelar.
        verbose: Pongase en False para que no se muestren mensajes en consola.
        return: Devuelve True si se ejecuta correctamente. False si ocurre un error. 
        '''
        try:
            count = 0
            if verbose:
                print('{} - Searching for pending orders of the strategy...'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), strategyId))
            for order in self.openOrders():
                if self.orderIdManager.is_order_child_of_strategy(order.orderRef, strategyId):
                    if verbose:
                        print('   Order canceled', order.orderRef)
                    self.cancel_order(order)
                    count += 1
                self.sleep(0)   # Garantiza el funcionamiento asyncrono
            msg = '{} pending orders of the strategy {} have been canceled'.format(count, strategyId)
            if verbose:
                print(f'   {msg}')
            self.log.info(msg)
            return True
        except Exception as e:
            self.log.exception('Error canceling strategy orders {}'.format(strategyId))
            return False



    def cancel_order(self, order, awaitSeconds=10):
        '''
        Ordena cancelar una orden y espera un tiempo a que termine.
        order: Es un objeto que representa a la orden.
        awaitSeconds: Cantidad de segundos maximos que se debe esperar.
        return: Retorna True si logra cancelar antes del tiempo de espera.
        '''
        try:
            self.cancelOrder(order)
            while awaitSeconds > 0:
                if not self.order_exist(order.orderRef):
                    return True
                self.sleep(1)   # Garantiza el funcionamiento asyncrono
                awaitSeconds -= 1              
            return False
        except Exception as e:
            self.log.exception(str(e))
            return False



    def order_exist(self, orderID):
        '''Devuelve True si la orden especificada existe.'''
        try:
            return len(list(filter(lambda x: x.orderRef == orderID, self.openOrders()))[0]) > 0
        except:
            return False
        


    def get_timestamp_for_seconds(self, seconds):
        '''Devuelve el DateTime correspondiente a la fecha actual mas los segundos indicados.'''
        return datetime.now() + timedelta(seconds=seconds)



    def can_relaunch_strategy(self, market, nowDateTime, lastDateTime, reconnection):
        '''Check if the strategy can be launched.'''
        marketOpen = self.tradingCalendar.market_open(market, lastDateTime, verbose=True)
        return not (not marketOpen and not self.configuration['relaunch_if_market_closed'])



    def reset_strategies(self, lastDateTime, reconnection):
        if reconnection:
            text = f'The connection has been lost since {lastDateTime}'
        else:
            text = f'The script has not been executed since {lastDateTime}'
        print(text)
        self.log.info(text)
        telegram.send_to_telegram(text, self.configuration)   
        noRelaunch = []            
        for stratgy in self.parameters.strategies:
            if not self.can_relaunch_strategy(stratgy['exchange'], datetime.now(), lastDateTime, reconnection):
                noRelaunch.append(stratgy)
                text = f"The strategy {stratgy['strategyId']} will not be restarting."
                print(text)
                self.log.info(text)
                telegram.send_to_telegram(text, self.configuration)   
            else:
                text = f"Restarting strategy {stratgy['strategyId']}"
                print(text)
                self.log.info(text)
                telegram.send_to_telegram(text, self.configuration)   
                self.cancel_orders_of_strategy(stratgy['strategyId'], verbose=True)
        self.parameters.strategies = noRelaunch



    def read_heart_beat(self, verbose=False):
        '''Devuelve el dato del fichero heartbeat.txt'''
        HEARTBEAT = 'heartbeat.txt'
        try:
            with open(HEARTBEAT, 'r') as file:
                line = file.readline().split('--')[0].rstrip()
                return datetime.strptime(line, "%Y-%m-%d %H:%M:%S.%f")
        except Exception as e:
            text = f'Error reading {HEARTBEAT}  Exception: {str(e)}'
            if verbose: print(text)
            self.log.info(text)
            return None



                
#print(LimitOrder('BUY', 10, 12.99, outsideRth=True, tif="GTC", orderRef='order101'))


