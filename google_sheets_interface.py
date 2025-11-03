
'''
Crea un objeto para leer o escribir datos en una hoja de calculo Google Sheets.
Creado: 16-09-2023
'''
__version__ = '1.0'

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow,Flow
from google.auth.transport.requests import Request
import os
import pickle
import logging 

from ib_insync import *


SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Este es el nombre del primer parametros de la tabla.
# Cada vez que el objeto lea un parametro con este nombre, va a asumir que se 
# ha empezado a leer una tabla. SI ya se estaba leyendo una tabla va a asumir 
# que la tabla anterior se termino y que ha comenzado otra tabla.
# Este sistema permite crear tablas con diferentes estructuras y longitudes
# de manera que cada estrategia puede tener su propia cantidad de parametros.
TABLE_BEGIN = 'strategyId'


class GoogleSheetsInterface:
    
    def __init__(self, credentials, sheetID, token=None):
        '''
        Crea un objeto para leer o escribir datos en una hoja de calculo Google Sheets.

        Parametros:
        credentials: Ruta completa del fichero de credenciales de Google. 
                     Ejemplo 'C:/New Frontier/credentials.json'
        sheetID: Es el ID de la hoja de calculo de la quie se deben leer los datos.
                 Ejemplo '1JOe2rzWEkciQasrhjsVFVesUCMIe5BuQXaeRWD-0QV5'
        beginRow: Número de fila donde empieza a leer las tablas.
        beginColumn: Número de columna donde empieza a leer las tablas.
        token: Establece la ruta donde se debe guardar el fichero token de acceso a
            la hoja de calculo. Debe ser una ruta terminada en el simbolo '/'.
            Ejemplo 'C:/New Frontier/'
            Si no se especifica este parametro, por defecto el fichero de token
            sera guardado en el directorio actual del script.
        '''
        self.credentials = credentials
        self.sheetID = sheetID
        self.token = './token.pickle' if token is None else token
        self.log = logging.getLogger('grid')



    def read_tables(self, page=None, beginColumn=1, beginRow=1, columns=2, rows=300, verbose=False):
        '''
        Lee las tablas de parametros desde la hoja actual de calculo Google Sheets
        
        Contexto: Se conecta a la hoja de calculo Google Sheets y lee en la pagina
        indicada las tablas que se encuentran en el rango especificado.
        Las tablas estan compuesta por dos columnas sin cabeceras.
        La primera columna de las tablas de la hoja de calculo deben contener los nombres
        de las variables y la segunda columna debe contener los valores. Los nombres
        de variables de la primera columna de la tabla, deben empezar con caracteres
        alfabeticos. 

        return: Devuelve una lista de diccionarios, donde cada uno contiene la tabla 
                de parametros como una coleccion llave:valor. 
                Si ocurre un error, devuelve None.
                Las llaves de los pares del diccionario seran nombradas con los nombres de
                la primera columna de la tabla de la oja de calculo, pero los espacios 
                seran sustituidos por guion bajo '_'. No se tendrán en cuenta los espacios
                que están al inicio o al final.
        '''
        table = self.create_range(page, beginColumn, beginRow, columns, rows)
        try:
            creds = None
            if os.path.exists(self.token):
                with open(self.token, 'rb') as token:
                    creds = pickle.load(token)
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(self.credentials, SCOPES)
                    creds = flow.run_local_server(port=0)
                with open(self.token, 'wb') as token:
                    pickle.dump(creds, token)
            service = build('sheets', 'v4', credentials=creds)
            sheet = service.spreadsheets()
            sheetExecuteResult = sheet.values().get(spreadsheetId=self.sheetID, range=table).execute()
            tableData = sheetExecuteResult.get('values', [])        

            tables = []   
            parametersAsDictionary = {}
            rowIndex = beginRow
            for param in tableData:
                if len(param) > 0:
                    try:
                        paramName = self.create_param_name(param[0])
                        if paramName == TABLE_BEGIN:
                            if len(parametersAsDictionary) > 0:
                                tables.append(parametersAsDictionary)
                                parametersAsDictionary = {}
                            parametersAsDictionary['beginRow'] = rowIndex
                        if len(param) > 1:
                            parametersAsDictionary[paramName] = param[1]
                        else:
                            parametersAsDictionary[paramName] = None
                    except Exception as e:
                        msg = f'Error reading param from Google Sheets row {rowIndex}'
                        if verbose: print(msg)
                        self.log.exception(f'{msg} Error: {str(e)}')
                rowIndex += 1
            if len(parametersAsDictionary) > 0:
                tables.append(parametersAsDictionary)
            return tables    
        except Exception as e:
            msg = f'Error reading strategies from Google Sheets {str(e)}'
            if verbose: print(msg)
            self.log.exception(msg)
            return None



    def create_param_name(self, inputString):
        '''
        Receives a character string of one or more words and 
        unifies them to form a parameter name without spaces.
        '''
        return inputString.strip().replace(' ', '_')



    def string_to_float(self, inputString):
        '''
        Converts a Google Sheet float to a Python float.
        inputString: String of characters that represents a floating number, which
                     uses a comma instead of a period as a decimal separator.
        Returns a float with the value represented by the string or returns None if an error occurs.
        '''
        try:
            return float((inputString.replace('.', '')).replace(',', '.'))
        except:
            return None



    @staticmethod
    def float_to_string(inputFloat):
        '''
        Convierte un float de Python en un float de Google Sheet.
        Devuelve un float con el valor representado por la cadena o devuelve
        Devuevle cadena vacia si ocurre un error.
        '''
        try:
            return str(inputFloat).replace('.', ',')
        except:
            return ''



    def create_range(self, page=None, beginColumn=1, beginRow=1, columns=2, rows=300):
        '''
        Devuelve un rango de celdas como cadena
        
        Parametros
        beginColumn:  Número de columna (mayor que cero) donde comienza la tabla en la hoja de cálculo.
        beginRow: Número de fila (mayor que cero) donde comienza la tabla en la hoja de cálculo.
        columns: Cantidad de columnas que tiene la tabla.
        rows: Cantidad de filas que tiene la tabla.
        
        Resultado
        Devuelve el rango de celdas correspondientes en la hoja de cálculo
        de Google Sheets. Ejemplo "A2:C8"
        Si alguno de los valores es menor o igual que cero, devuelve None.
        Si beginColumn+columns >= 130, devuelve None, pues solo se permite hasta la columna 130.
        '''
        columnsLabels = [
            'A','B','C','D','E','F','G','H','I','J','K','L','M',
            'N','O','P','Q','R','S','T','U','V','W','X','Y','Z',
            'AA','AB','AC','AD','AE','AF','AG','AH','AI','AJ','AK','AL','AM',
            'AN','AO','AP','AQ','AR','AS','AT','AU','AV','AW','AX','AY','AZ',
            'BA','BB','BC','BD','BE','BF','BG','BH','BI','BJ','BK','BL','BM',
            'BN','BO','BP','BQ','BR','BS','BT','BU','BV','BW','BX','BY','BZ',
            'CA','CB','CC','CD','CE','CF','CG','CH','CI','CJ','CK','CL','CM',
            'CN','CO','CP','CQ','CR','CS','CT','CU','CV','CW','CX','CY','CZ',
            'CA','CB','CC','CD','CE','CF','CG','CH','CI','CJ','CK','CL','CM',
            'CN','CO','CP','CQ','CR','CS','CT','CU','CV','CW','CX','CY','CZ'
        ]
        if beginRow > 0 and beginColumn > 0 and rows > 0 and columns > 0 and beginColumn + columns < len(columnsLabels):
            beginColumn -= 1
            page = '' if page is None else page+'!'
            return '{}{}{}:{}{}'.format(
                str(page),
                str(columnsLabels[beginColumn]), 
                int(beginRow), 
                str(columnsLabels[beginColumn + columns - 1]), 
                int(beginRow + rows - 1)
            )
        else:
            return None



    def is_active(self, value): 
        if value == 'SI':
            return True
        elif value == 'NO':
            return False
        else:
            return False



    def str_to_boolean(self, value):
        if value == 'TRUE':
            return True
        elif value == 'FALSE':
            return False
        else:
            return False



    def get_google_service(self):
        """
        Authenticates and obtains a Google Sheets service instance for interaction.
        Returns: object or None: A Google Sheets service instance or None if there's an error.
        """
        token = None
        try:
            creds = None
            tokenFile = './token.pickle' if token is None else token
            if os.path.exists(tokenFile):
                with open(tokenFile, 'rb') as token:
                    creds = pickle.load(token)
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(self.sheetID, SCOPES)
                    creds = flow.run_local_server(port=0)
                with open(tokenFile, 'wb') as token:
                    pickle.dump(creds, token)
            service = build('sheets', 'v4', credentials=creds)
            return service 
        except Exception as e:
            # Capture and display any exceptions that occur
            self.log.exception(f'Error authenticating with Google Sheets: {str(e)}')
            return None



    def write_data_to_sheet(self, sheet_name, data, service = None, start_column = "A", start_row = 1):
        """
        Writes data to a specified sheet in Google Sheets begining in column A row 1 (default).

        Args:
            table (str): The range in R1C1 notation where the data should be written.
            data (list): The data to be written.
            service (object): The Google Sheets service object.
            start_column (str): The initial column (e.g., 'A', 'B', 'C').
            start_row (int): The initial row (e.g., 1, 2, 3).        

        Returns:
            dict or None: The response from the Google Sheets API or None if there's an error.
        """
        table = self.get_R1C1_Notation (sheet_name, start_column, start_row, data)
        
        try:
            response = service.spreadsheets().values().update(
                spreadsheetId= self.sheetID,
                range=table,
                body={'values': data},
                valueInputOption='RAW'
            ).execute()
            return response

        except Exception as e:
            # Capture and display any exceptions that occur
            self.log.exception(f'Dashboard Error: {str(e)}')
            return None



    def insert_data(self, sheet_name, data, service = None, begin_row = 1):
        """
        Inserts rows with data into the given sheet of a Google Sheets document,
        starting on begin_row.
        Args:
            sheet_name (str): The name of the target sheet.
            begin_row: row in which data is inserted (default is 1 to leave headers at the top)
            data (list): The data to be inserted as a list of lists.
            service (object): The Google Sheets service object.
        Returns:
            dict or None: The response from the Google Sheets API or None if there's an error.
        """
        
        try:
            # core.dashBoard.isUpdating = True
            # Get the sheet ID based on the sheet name
            data = [data]
            if not service: service = self.get_google_service()
            spreadsheet = service.spreadsheets().get(spreadsheetId=self.sheetID).execute()
            sheet_id = None
            for sheet in spreadsheet['sheets']:
                if sheet['properties']['title'] == sheet_name:
                    sheet_id = sheet['properties']['sheetId']
                    break
            if sheet_id is None:
                self.log.error(f'Sheet "{sheet_name}" not found in the spreadsheet.')
                return
            # Insert rows with data into the sheet
            start_index = begin_row + 1  # Start inserting rows below header row
            end_index = start_index + len(data) - 1
            request_body = {
                "requests": [
                    {
                        "insertDimension": {
                            "range": {
                                "sheetId": sheet_id,
                                "dimension": "ROWS",
                                "startIndex": start_index - 1,  # Adjust for 0-indexed sheet
                                "endIndex": end_index
                            },
                            "inheritFromBefore": False
                        }
                    },
                    {
                        "pasteData": {
                            "coordinate": {
                                "sheetId": sheet_id,
                                "rowIndex": start_index - 1,  # Adjust for 0-indexed sheet
                                "columnIndex": 0
                            },
                            "data": "\n".join(["\t".join(map(str, fila)) for fila in data]),        
                            "type": "PASTE_NORMAL",
                            "delimiter": "\t"
                        }
                    }
                ]
            }
            response = service.spreadsheets().batchUpdate(
                spreadsheetId=self.sheetID,
                body=request_body
            ).execute()
            return response
        except Exception as e:
            # Capture and display any exceptions that occur
            self.log.exception(f'Dashboard Error: {str(e)}')
            return None



    # Translates a column number into shett letters like  AZ or CB
    def _column_number_to_excel_letters(self, column_number):
        letters = ""
        while column_number > 0:
            remainder = (column_number - 1) % 26
            letters = chr(ord("A") + remainder) + letters
            column_number = (column_number - 1) // 26
        return letters



    # Returns range in excel notation
    def get_R1C1_Notation(self, sheet_name, start_column, start_row, data):
        """
        Returns a range in the format "Sheet!A1:B2" based on the sheet name, starting
        column, starting row, and a two-dimensional table.

        Args:
            sheet_name (str): The name of the sheet.
            start_column (str): The initial column (e.g., 'A', 'B', 'C').
            start_row (int): The initial row (e.g., 1, 2, 3).
            data (list of lists): A two-dimensional table.

        Returns:
            str: The range in R1C1 notation.
        """
        
        try:
            # Calculate the ending row and column based on the data dimensions
            end_row = start_row + len(data) - 1
            end_column = self._column_number_to_excel_letters(ord(start_column) - 65 + len(data[0]))
            
            # Construct the R1C1 notation
            range_notation = f"{sheet_name}!{start_column}{start_row}:{end_column}{end_row}"

            return range_notation
        except Exception as e:
            self.log.exception(f"get_R1C1_Notation Error: {e}")



def test():    
    '''Para probar el funcionamiento de esta libreria'''
    import json
    CREDENTIALS = 'C:/New Frontier/credentials.json'
    DOCUMENT_ID = '1JOe2rzWEkciQasrhjsVFVesUCMIe5BuQXaeRWD-0QV4'
    multitables = GoogleSheetsInterface(CREDENTIALS, DOCUMENT_ID)
    result = multitables.read_tables('Estrategias')
    print(json.dumps(result, indent=2))



if __name__ == "__main__":
    test()




