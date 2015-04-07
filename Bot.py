#!/usr/bin/env python

from betfair.api import API
from sys import exit
from time import sleep
import datetime, os, time

# ---------------- variables para configurar ------------------------
username = 'user' # usuario betfair (entre comillas simples o dobles)
password = 'password' # password betfair (entre comillas simples o dobles)
horas = 8 # horas que quieres capturar en get_all_markets()
trigger = 30 # cuantos segundos antes de que empiece el evento se lanza la apuesta
stake = 2 # stake (dinero) para cada apuesta (con 2 decimales maximo separados por punto, MINIMO 2 EUROS)
stop_loss = 20 # cantidad de dinero que estas dispuesto a perder por dia (con 2 decimales maximo separados por punto)
cuota_minima = 2.0 # cuota minima que queremos tener en la apuesta (con 2 decimales maximo separados por punto)
reservas = False # True (apuesta) aunque haya reserva, False (no apuesta) si hay reserva
comision = 0.06 # comision del 6%
# ---------------- fin variables para configurar ---------------------
revision = int(round(float(stop_loss) / stake)) # calcula las carreras necesarias para revisar el stop-loss
apuestas = 0 # contador de apuestas para revisar el stop-loss

# create new API object
exchange = 'uk' # OR 'aus'
bot = API(exchange)

# login
if not username or not password:
    print 'ENTER YOUR USERNAME AND PASSWORD INTO example.py BEFORE RUNNING!'
    exit()
print 'Login:', bot.login(username, password)

# logout
def salir():
	print "Logout:", bot.logout()
	exit()

# get account funds
funds = bot.get_account_funds() # funds = dict of account info
print 'Funds:', funds['availBalance']
print 'Current Exposure:', funds['exposure']

# fichero con nombre tipo fecha day-month-year.txt
fichero = datetime.datetime.utcnow().strftime('%d-%m-%y') + '.txt'
# cargamos fichero creando una lista
f = open(fichero, 'r')
pronosticos = f.readlines()
f.close()

# creamos una lista de listas con ['hora','canodromo','galgo']
for i in range(len(pronosticos)):
  pronosticos[i] = pronosticos[i].split()
# eliminamos filas vacias del fichero de los pronosticos para evitar errores.
for prono in pronosticos[:]:
  pronosticos.remove(prono)  
  if len(prono) != 0 :	
	pronosticos.append(prono)

# ordenamos la lista por su valor en lista[0] (la hora de la carrera)
pronosticos.sort(key=lambda lista: lista[0])

'''Adquirimos la hora de UK para compararla con UTC(servidor betfair).
Si UK tiene horario de verano(DST(UTC+1)) cambiamos la hora de los pronosticos para que coincida con
el servidor de betfair'''
os.environ['TZ'] = 'Europe/London'
time.tzset()
hora_uk = time.strftime('%H:%M')
hora_utc = datetime.datetime.utcnow().strftime('%H:%M')
print 'Hora de UK: %s\nHora de UTC: %s' % (hora_uk, hora_utc)
if (hora_uk > hora_utc) :
	print 'Cambiando la hora de las carreras...\n'
	for i in range(len(pronosticos)):
		hora = str(int(pronosticos[i][0].split(':')[0]) - 1) + ':' + pronosticos[i][0].split(':')[1]
		pronosticos[i][0] = hora	
else:
	print 'UK con hora UTC, horarios sin cambios.\n'

# eliminar carreras ya corridas
while len(pronosticos) > 0 :
	if hora_utc > pronosticos[0][0]:
		del pronosticos[0]
	else:
		break
print 'Found', len(pronosticos), 'pronosticos.'

# get all markets starting within the next hours or minutes
markets = bot.get_all_markets(
                events = ['4339'], # greyhound racing
                hours = horas, # = 0.5, # starting in the next 30 mins (0.25 = 15 mins, 2 = 120 mins, etc)
                include_started = False, # exclude in-play markets
                countries = ['GBR'] # British racing only
                )

# sort markets by start time + filter
if type(markets) is list:
            for market in markets[:]: # loop through a COPY of markets as we're modifying it on the fly...
                markets.remove(market)
                if (market['bsp_market'] == 'Y' # BSP markets only
                    and market['market_name'] != 'Forecast' # NOT forecast markets
                    and market['market_status'] == 'ACTIVE' # market is active
                    and market['market_type'] == 'O' # Odds market only
                    and market['no_of_winners'] == 1 # single winner market
                    ):
                    # calc seconds til start of race
                    delta = market['event_date'] - bot.API_TIMESTAMP
                    sec_til_start = delta.days * 86400 + delta.seconds # 1 day = 86400 sec
                    temp = [sec_til_start, market]
                    markets.append(temp)
            markets.sort() # sort into time order (earliest race first)
print 'Found', len(markets), 'markets.'

def next_race(market, galgo = '0'):
	if galgo != '0':
		print '-'*10 + ' Siguiente pronostico ' + '-'*10
	else:
		print '-'*10 + ' Siguiente carrera ' + '-'*10
	print 'Hora: ', market[1]['event_date'].strftime('%H:%M')
	print 'Corredores: ', market[1]['no_of_runners']
	print 'Canodromo: ', market[1]['menu_path'].lstrip('\\').split('\\')[2].split()[0]
	if galgo != '0':
		print 'Seleccion: ', galgo + '\n'
	else:
		print

next_race(markets[0])

def wait(market):
	global trigger
	delta = market[1]['event_date'] - datetime.datetime.utcnow()
	sec_til_trigger = (delta.days * 86400 + delta.seconds) - trigger	
	if sec_til_trigger > 1200: # si hay que esperar mas de 20 minutos, mantenemos conexion con keep alive
		while sec_til_trigger > 1200:
			print 'Esperando 20 minutos hasta hacer un keep alive...'
			sleep(1200)
			print 'keep alive: %s' % bot.keep_alive()
			sec_til_trigger -= 1200
	if sec_til_trigger > 0:
		print 'Esperando %d minutos y %d segundos hasta lanzar la apuesta (trigger)...' % (sec_til_trigger/60,sec_til_trigger%60)
		sleep(sec_til_trigger)

# creamos las variables fuera para no crearlas a cada llamada de la funcion
year = int(time.strftime('%Y'))
month = int(time.strftime('%m'))
day = int(time.strftime('%d'))

def profit_loss(balance = 0):
	global stake, stop_loss, revision, apuestas, year, month, day, comision
	p_l = 0.0
	profit = bot.get_bet_history(event_type_ids = ['4339'], market_types_included = ['O'],
		placed_date_from = datetime.datetime(year, month, day), placed_date_to = datetime.datetime(year, month, day, 23, 59))
	if balance and type(profit) is dict: # para mirar balance despues de cada carrera
		for copy in profit['bets']: # calculamos la ganancia_perdida
			if float(copy['profitAndLoss']) < 0 :
				p_l += float(copy['profitAndLoss'])
			else:
				p_l += float(copy['profitAndLoss']) - (float(copy['profitAndLoss']) * comision)
		print '\n' + '#'*15 + ' P&L: %.2f ' % p_l + '#'*15 + '\n'
	elif type(profit) is dict: # para calcular el stop-loss
		apuestas = 0 # reiniciamos contador de apuestas
		for copy in profit['bets']: # calculamos la ganancia_perdida
			if float(copy['profitAndLoss']) < 0 :
				p_l += float(copy['profitAndLoss'])
			else:
				p_l += float(copy['profitAndLoss']) - (float(copy['profitAndLoss']) * comision)
		print '\n' + '#'*15 + ' P&L: %.2f ' % p_l + '#'*15 + '\n'
		if (p_l - -stop_loss) >= stake: # si aun podemos hacer alguna carrera, calculamos cuantas
			dinero_hasta_alcanzar_stop_loss = p_l - -stop_loss
			revision = int(round(float(dinero_hasta_alcanzar_stop_loss) / stake))
			print '(Proxima revision de stop-loss en %d carreras)\n' % revision
		else:
			s = '!!STOP-LOSS ALCANZADO!! CERRANDO SESION...\n'
			print '-' * len(s) + '\n' + s + '-' * len(s)
			salir()
	else:
		print 'ERROR en funcion profit_loss(): %s' % profit

# get prices for the first market (we could loop through all of them at this point)
if type(markets) is list: # type-check response as it could be an error string
    if len(markets) > 0:
	while len(pronosticos) > 0:
		# buscamos en markets la primera carrera que tenemos en la lista pronosticos
		while len(markets) > 0 and len(pronosticos) > 0:
			hora = markets[0][1]['event_date'].strftime('%H:%M')
			canodromo = markets[0][1]['menu_path'].lstrip('\\').split('\\')[2].split()[0]
			if pronosticos[0][0] < hora :
				# si fallamos datos escribiendo el pronostico, se cancela esa carrera o no capturamos el market de esa carrera
				# para no quedarnos bloqueados en la carrera y pasar a la siguiente
				print 'CARRERA OBSOLETA, CANCELADA O MAL CONFIGURADA:'
				print 'Hora: %s - Canodromo: %s - Galgo: %s' % (pronosticos[0][0],pronosticos[0][1],pronosticos[0][2])
				del pronosticos[0]
			elif pronosticos[0][0] == hora and pronosticos[0][1].title() == canodromo.title() :
				break
			else:
				del markets[0]
		# si el anterior while nos deja sin pronosticos, salimos
		if len(pronosticos) == 0:
			break

		market = markets[0]
		# anunciamos la siguiente carrera		
		next_race(market, pronosticos[0][2])
		# esperamos x segundos (trigger) para entrar la apuesta
		wait(market)

		# revisar el stop-loss
		if apuestas == revision:
			profit_loss()
		else: # miramos balance
			profit_loss(1)

		# miramos si nuestro galgo es baja y hay vacante o reserva
		search_dog = bot.get_market(market[1]['market_id'])
		vacante = True
		cuota_baja = True
		if type(search_dog) is dict:			
			for galgo in search_dog['runners']:
				# si encontramos el galgo y no es reserva, procedemos
				if galgo['name'][0] == pronosticos[0][2] and (galgo['name'][-5:].title() != '(Res)' or reservas):
					seleccion_id = galgo['selection_id']
					# obtener precios y apostar		
					print 'Getting prices for market id:', market[1]['market_id']
					prices = bot.get_market_prices(market[1]['market_id']) # prices = full market info
					if type(prices) is dict and len(prices['runners'][0]['back_prices']) > 0:
						for runner in prices['runners']:
							if runner['selection_id'] == seleccion_id:
								precio = runner['back_prices'][0]['price']
								vacante = False
								# miramos que cumpla cuota minima
								if precio >= cuota_minima:
									cuota_baja = False
								break
					else:
						print 'get_market_prices() ERROR:', prices
						
					break
		else:
			print 'get_market() ERROR:', search_dog
		
		# creamos la apuesta y la lanzamos
		if not vacante and not cuota_baja:
			# print prices
			print 'Found prices for', len(prices['runners']), 'runners:'
			# print para ver todos los precios (se puede quitar si se quiere)
			for runners in prices['runners']:
				print 'T%s: Back: %.2f - Lay: %.2f' % (runners['order_index'],runners['back_prices'][0]['price'],runners['lay_prices'][0]['price'])


			print '\nPrecio: %.2f - Id: %s' % (precio, seleccion_id)
			# construimos el dict con los datos de la apuesta
			print 'Placing bets...'
			# build the bets list
			bets = []
			bet = { 'marketId': market[1]['market_id'],
				'selectionId': seleccion_id, #runner['selection_id'],
				'betType': 'B', # B = Back, L = Lay
				'price': '%.2f' % precio,
				'size': '%.2f' % stake, #'2.00',
				'betCategoryType': 'E',
				'betPersistenceType': 'NONE',
				'bspLiability': '0',
				'asianLineId': '0'
				}
			bets.append(bet)		    

			# place the bets
			if bets:				
				#exit()
				resp = bot.place_bets(bets)
				del pronosticos[0]
				if type(resp) is list:
					print 'Place bets response:', resp, '\n'
					# llevar la cuenta de las apuestas para mirar el stop_loss
					apuestas += 1
				else:
					print 'place_bets() ERROR:', resp
		elif vacante:
			print 'Galgo seleccionado AUSENTE! Trap vacante o con reserva.'
			print 'Hora: %s - Canodromo: %s - Galgo: %s' % (pronosticos[0][0],pronosticos[0][1].title(),pronosticos[0][2])
			del pronosticos[0]
		else:
			print 'Cuota fuera de rango! Carrera descartada.'
			print 'Hora: %s - Canodromo: %s - Galgo: %s - Cuota: %.2f' % (pronosticos[0][0],pronosticos[0][1].title(),pronosticos[0][2],precio)
			del pronosticos[0]
    else:
        print 'NO MARKETS FOUND!'
else:
    print 'get_all_markets() ERROR:', markets

# logout
print 'No hay mas pronosticos, saliendo...'
salir()

