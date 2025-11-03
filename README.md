<h1>Grid Bot para Interactive Broker</h1>

<p>Este es un Grid Bot para Interactive Broker con manejo de riesgo que emplea la librearía de Python "ib_insync". Fue realizada para el cliente Manuel Polavieja de España, quien suministró el método de cálculo de riesgo y dirigió el proceso de implementación. El cliente suministró un código inicial con funciones y métodos propios que no se han publicado en este repositorio para respetar el derecho del autor, y luego se extendieron las funcionalidades del Bot para finalmente realizar lo siguiente:</p>

- Muestra datos en un DashBoard en Google Sheet.
- Se controla mediante parámetros de una hoja de Google Sheet.
- Permite ejecutar multiples instancias del algoritmo y controlarlos en Google Sheet.
- Contabiliza y limita el riesgo que mantiene el Bot durante su funcionamiento.
- Envía datos a un canal o usuario de Telegram.
- Mantiene ficheros LOG con los datos de ejecución del Bot.
- Mantiene un calendario interno de los horarios de funcionamiento de los mercados.

<h2>El trabajo que realicé consiste básicamente en emplementar las clases:</h2>

<h3>TradingCalendar</h3>
<p>Esta es una clase que permite crear un registro de los horarios de apertura y cierre de los mercados de interés, sus zonas horarias y excepciones como son navidad, y otros días feriados. Los datos de los mercados deben declararse dentro de la constante "TRADING_SESSIONS" siguiendo como ejemplo los mercados que ya estan contenidos en la estructura. Para conocer si el mercado está abierto se emplea el método "market_open()".</p>

<h3>RiskManager</h3>
<p>Este es un aclase que contabiliza el riesgo que mantiene en cada momento en bot de trading. Contabiliza el riesgo con un metodo especificado por Manuel Polavieja. Básicamente tiene un método llamado "can_operate()" que devuelve True si es posible realizar operaciones teniendo en cuenta el nivel de riesgo actual.</p>

<h3>OrderIdManager</h3>
<p>Crea una clase para el manejo de los ID de las ordenes de compra y venta.
El exchange permite agregar a cada orden un ID que es un número entero y esta clase se emplea para empaquetar dentro de ese número otros valores importantes para la administración e identificación de las órdenes. También tiene el metodo para desempaquetar los valores contenidos en el ID de la orden y otros métodos auxiliares para saber si un identificador pertenece a un cliente o estrategia específica. El ID permite relacionar una orden con una instancia del cliente y con una ejecucion dentro de la misma instancia del cliente. Los valors que se guardan son:</p>

 - Identificador del cliente
 - Identificador del contrato
 - Identificador de la estrategia que se está ejecutando.
 - Dirección de la operación Buy/Sell
 - Número de la orden

<h3>GoogleSheetsInterface</h3>
<p>Crea un objeto para leer o escribir datos en una hoja de calculo Google Sheets.</p>

<h3>MultiParameters</h3>
<p>Crea un objeto para manejar los parametros de funcionamiento del bot.
Esta clase es una abstrapción para evitar que el bot baneje directamente el almacanamiento de datos que es una hoja de Google Sheet pero a futuro será posible cambiarlo por una database. Tiene métodos que facilitan la obtenció y filtrado de los parámetros.</p>

<h3>Core</h3>
<p>Crea un objeto que representa al broker o exchange. Esta clase extiende las propiedades y metodos de la clase IB de la librería ib_insync agregándole los métodos necesarios para el manejo del Grid Bot.</p>

<h3></h3>
<p></p>


