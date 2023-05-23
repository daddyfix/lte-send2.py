#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ChangeLog
May 23 2022
    - bug fixes
Oct 30 2020
    - bug fixes
Dec 20 2019
	- added resize of andimated gif with python gifsicle
Sep 29 2019
	- added resize image option -z --imgresize
May 23 2019
	- fixed bug on imgnodelete. Added -nodelete
April 3 2019
	- add multiple mobile recipients.
	  Now can add multiple mobile numbers separated by comma (,) ie. 7058881111,7058882222
	  If there is multiple mobile numbers then all messages are sent using BCC
	  If there is only one number then numnber is sent standard way

"""

""" ----------------------------------------------------------

	Install Modules if not installed

---------------------------------------------------------- """
import pip, time, sys
for im in ["serial", "humanfriendly", "magic", "python-dateutil", "Pillow"]:
	try:
		pkg = im
		if 'dateutil' in im:
			pkg='dateutil'
		elif 'Pillow' in im:
			pkg='PIL'
		globals()[pkg] = __import__(pkg)
	except ImportError:
		if 'Pillow' in im:
			print ("Cannot install Pillow via pip install")
			print ("Please install via ...")
			print ("sudo apt-get install python-imaging")
			sys.exit()
		print ("Installing "+im+" module...")
		pip.main(['install', im])
		time.sleep(2)


""" ------------------------------------------------------------

	Import Modules

-------------------------------------------------------------"""
# PySerial
import serial
import serial.tools

# System
import datetime
from datetime import timedelta
import dateutil
from dateutil import parser
from dateutil import tz
import inspect
import os
import logging
import glob
import json
import time

# Convertions
import humanfriendly
import magic
import PIL
from PIL import Image

#sys.exit()
# Load Python file as args
import ast

# Regex
import re

# Parse the Arguments passed to this script
import argparse

# URL/Web Functions
import urllib
import urllib.request
import urllib3
import urlparse2

# Database
import sqlite3
from sqlite3 import Error

# Run Linux Scripts
import subprocess

#Global Variables
ser = False

# Is there a READ SMS service running in the background?
# If gammu or smstools then do you want this script to restart the service after send/read?
gammu_service_force_start = False    # make sure gammu-smsd.service is running after output_close
smstools_service_force_start = True    # make sure smstools.service is running after output_close

debug = False
custom_at_command = False
#debug = True

errorcodes =  False
textfile_holder=''
imagefile_holder=''
saved_image_files=[]
gConn=None

# Paths and Log Filenames
filename = inspect.getframeinfo(inspect.currentframe()).filename
modem_files_path = os.path.dirname(os.path.abspath(filename))+'/modem_tmp_files/'
modem_file_cutoff_in_days = 10
imagepath = '/nfs/nas/data/live/servers/mobilesvr/movie_posters/'
send_bulk_mms_path = os.path.dirname(os.path.abspath(filename))+'/send-bulk-mms/images/'
filebase = os.path.splitext(filename)[0]
logfile = '/nfs/nas/data/live/servers/mobilesvr/logs/lte-send.py.log'
sendlist = '/nfs/nas/data/live/servers/mobilesvr/logs/text-message-sent-list.txt'
errorCodesFile = os.path.dirname(os.path.abspath(filename))+'/errorcodes.py'
atfile = os.path.dirname(os.path.abspath(filename))+'/at_commands.txt'
dbpath = '/nfs/nas/data/live/servers/mobilesvr/database/'
DBFILE = dbpath+'mobilesvr.db'
database_reachable = os.path.isfile(DBFILE)

# Connection Details
default_baudrate='115200'
#default_baudrate='9600'
default_port='/dev/ttyUSB3'
default_output='json'

# Image Processing
# -----------------------
# Time in seconds before the 1st image is downloaded
default_img_delay = '0'
# Number of images to gather from the source URL/Filename
default_img_qty = '1'
# Time in seconds to wait between gathering images
default_img_qty_delay = '2'
# Do not delete the image file from disk. False equals delete file
default_img_no_delete = False
# Resize the image file to 400x400 (width,height)
default_img_size = 500
# Image Max filesize in bytes. gif images are ignored
max_image_filesize = 300000

# For Logging
# ------------------------
default_mqttid = ''
default_friendlytitle = ''


logging.basicConfig(filename=logfile,level=logging.DEBUG)
#logging.debug('This message should go to the log file')
#logging.info('So should this')
#logging.warning('And this, too')

# Trim files
rc = subprocess.call("echo \"$(tail -n 150 "+logfile+")\" > "+logfile, shell=True)
rc = subprocess.call("echo \"$(tail -n 150 "+atfile+")\" > "+atfile, shell=True)
rc = subprocess.call("echo \"$(tail -n 400 "+sendlist+")\" > "+sendlist, shell=True)


"""
QUERY/SET MMS SETTINGS

Change the below to match your mobile providers settings

Each dict has 4 parts
desc - description of the AT Command
query - AT Command to query a setting
expected - search string for valid response
correct - AT Command to set the Setting to desired Params
ltemobile.apn
"""
modem={}
modem[0]    = { 'desc' : 'APN details',
					'query': 'AT+QICSGP=1', 
					'expected': '"ltemobile.apn","",""', 
					'correct': 'AT+QICSGP=1,1,"ltemobile.apn","","",0'}
modem[1]    = { 'desc' : 'Context ID',
					'query': 'AT+QMMSCFG="contextid"', 
					'expected': '"contextid",1', 
					'correct': 'AT+QMMSCFG="contextid",1'}
modem[2]    = { 'desc' : 'Mult Media Service Centre',
					'query': 'AT+QMMSCFG="mmsc"', 
					'expected': 'mms.gprs.rogers.com', 
					'correct': 'AT+QMMSCFG="mmsc", "http://mms.gprs.rogers.com"'}
modem[3]    = { 'desc' : 'Provider Proxy Details',
					'query': 'AT+QMMSCFG="proxy"', 
					'expected': '10.128.1.69', 
					'correct': 'AT+QMMSCFG="proxy","10.128.1.69",80'}
'''
modem[4]    = { 'desc' : 'Character Set',
					'query': 'AT+QMMSCFG="character"', 
					'expected': 'UTF8', 
					'correct': 'AT+QMMSCFG="character","UTF8"'}
'''
modem[5]    = { 'desc' : 'Send Parameters',
					'query': 'AT+QMMSCFG="sendparam"', 
					'expected': '6,3,0,0,2,4', 
					'correct': 'AT+QMMSCFG="sendparam",6,3,0,0,2,4'}
modem[6]    = { 'desc' : 'Support Field',
					'query': 'AT+QMMSCFG="supportfield"', 
					'expected': '"supportfield",0', 
					'correct': 'AT+QMMSCFG="supportfield",0'}
'''
modem[7]    = { 'desc' : 'Network Registered Status',
					'query': 'AT+CREG?', 
					'expected': '+CREG: 0,1', 
					'correct': ''}
'''								
char_ascii={}
char_ascii[0]= { 'desc' : 'Character Set',
					'query': 'AT+QMMSCFG="character"', 
					'expected': 'ASCII', 
					'correct': 'AT+QMMSCFG="character","ASCII"'}


""" -------------------------------------------------------

	Database Functions

-------------------------------------------------------- """
def init_db_connection():
	global gConn
	global database_reachable

	if not database_reachable:
		return False

	if not os.path.isfile(DBFILE):
		debug_msg("- Sqlite Database: "+DBFILE+" does not exist. Creating DB...")
		gConn = sqlite3.connect(DBFILE)
		os.chmod(DBFILE, 0o766)
		create_table()
	elif gConn == None:
		debug_msg("- SQlite File Found: "+DBFILE)
		gConn = sqlite3.connect(DBFILE)

def get_db_connection():
	if gConn == None:
		init_db_connection()
	return gConn

def close_db_connection():
	global gConn
	if gConn != None:
		debug_msg("Closing DB Connection...")
		gConn.close()
		gConn = None
	
def get_cursor():
	if gConn == None:
		init_db_connection()
	return gConn.cursor()

def create_table(commit=True):
	#cur = get_cursor()
	get_db_connection().execute(
		''' CREATE TABLE IF NOT EXISTS 'msgs' (
				'id' INTEGER PRIMARY KEY NOT NULL,
				'mobile' TEXT NOT NULL,
				'msg' TEXT NOT NULL,
				'sent_at' DATETIME NOT NULL DEFAULT (DATETIME(CURRENT_TIMESTAMP, 'LOCALTIME')),
				'twofactor' TEXT DEFAULT '',
				'mqttid' TEXT DEFAULT '',
				'friendlytitle' TEXT DEFAULT ''
				); '''
		)


def table(action, details):

	global database_reachable

	if not database_reachable:
		return False

	do_sql=True
	if 'insert' in action:
		data = get_tuple_values(["mobile", "msg", "twofactor", "mqttid", "friendlytitle"], details)
		SQL_CMD = '''INSERT INTO msgs(mobile, msg, twofactor, mqttid, friendlytitle) VALUES(?,?,?,?,?)'''

	# elif 'update' in action:
	# 	data = get_tuple_values(["sent", "tries"], details)
	# 	if details['sent'] == 1:
	# 		data = data + (get_date() ,)
	# 	else:
	# 		data = data + ('',)
	# 	data = data + (details['id'] ,)
	# 	SQL_CMD = '''UPDATE send SET sent = ?, tries = ?, sent_date = ? WHERE id = ?'''

	elif 'delete' in action:
		days = int(details['days'])
		data = get_past_date(days)
		# DELETE FROM "send" WHERE "sent_date" < "2018-06-18 21:45:13"
		SQL_CMD = '''DELETE FROM msgs WHERE sent_at < ?'''

	else:
		do_sql=False

	if do_sql:
		# dynamically detect parameter type: tuple/list/string
		conn = get_db_connection()
		cur = get_cursor()

		debug_msg("Submitting SQL Query")
		debug_msg(" - "+SQL_CMD)

		do_commit = True
		if type(data) == list:
			cur.executemany(SQL_CMD, data)
		elif type(data) == tuple:
			cur.execute(SQL_CMD, data)
		elif type(data) == str:
			cur.execute(SQL_CMD, (data,))
		else:
			# unkown type
			do_commit = False
			pass
		if do_commit:
			conn.commit()
			return cur.lastrowid
	else:
		return False
		

def get_date():
	return (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

def get_past_date(val):
	past = datetime.datetime.now() - timedelta(days=val)
	return (past.strftime("%Y-%m-%d %H:%M:%S"))

""" --------------------------------------------------------------
	Database Functions END
-------------------------------------------------------------- """


""" --------------------------------------------------------------

	Image Manipulatiion

--------------------------------------------------------------- """
def resize_image(filename, size=default_img_size):
	debug_msg("Resizing: "+filename)
	img = Image.open(filename)
	
	# convert str to int
	new_size = ((int(size),int(size)))

	img.thumbnail(new_size, Image.BICUBIC)
	img.save(filename,optimize=True,quality=96)


"""
Make a tuple from a dictionary
"""
def get_tuple_values(mylist, details):

	newtuple=()
	for a in mylist:
		if a in details:
			newtuple= newtuple + (details[a] ,)

	return newtuple


"""
Print Messages to the screen and logfile
"""
def debug_msg(mystr, linefeed = True):

	mystr = str(mystr)
	if debug:
		sys.stdout.write(mystr)

		if linefeed:
		   sys.stdout.write("\n")

		sys.stdout.flush()

	logging.debug(get_date()+" ::: "+mystr)



""" --------------------------------------

	Send Output to console as json or text then exit

	arg list List of Dictionaries
	or
	arg list with 1 String arg
	or 
	arg string Sting status of query

------------------------------------------"""
def output_close(myobject):

	success = '{"status":"success","result":'
	error = '{"status":"error","result":'
	myoutput = "output_close: arg is not type str or list"

	global args, ser, gammu_service_force_start, smstools_service_force_start

	if not args['json']:
		if type(myobject) is list and type(myobject[0]) is dict:
			# we have no choice but to force json
			myoutput = json.dumps(myobject, indent=4)
		if type(myobject) is list:
			# we have no choice but to force json
			myoutput = ' '.join(myobject)
		elif type(myobject) is dict:
			myoutput = json.dumps(myobject, indent=4)
		elif type(myobject) is str:
			myoutput = myobject

	else:
		if type(myobject) is list:
			if type(myobject[0]) is str and len(myobject) == 1:
				if re.search("(?i)^error", myobject[0], re.IGNORECASE):
					myoutput = error+'"'+myobject[0]+'"}'
				else:
					myoutput = success+'"'+myobject[0]+'"}'
			else:
				data = json.dumps(myobject, indent=4)
				myoutput = success+data+'}'
		elif type(myobject) is str:
			if re.search("(?i)^error", myobject, re.IGNORECASE):
				myoutput = error+'"'+myobject+'"}'
			else:
				myoutput = success+'"'+myobject+'"}'
		else:
			myoutput = myobject

	print (myoutput)
	
	close_serial_connection()

	if gammu_service_force_start:
		p = subprocess.Popen("sudo systemctl start gammu-smsd",shell=True,stdout=subprocess.PIPE)
		time.sleep(2)
		p = subprocess.Popen("sudo lsof | grep "+ser.port,shell=True,stdout=subprocess.PIPE)
		line = p.stdout.readline()
		if line:
			debug_msg('Started gammu-smsd.service')
		else:
			debug_msg('Could not start gammu-smsd.service')
			error = True

	if smstools_service_force_start:
		p = subprocess.Popen("sudo systemctl start smstools",shell=True,stdout=subprocess.PIPE)
		time.sleep(2)
		p = subprocess.Popen("sudo lsof | grep "+ser.port,shell=True,stdout=subprocess.PIPE)
		line = p.stdout.readline()
		if line:
			debug_msg('Started smstools.service')
		else:
			debug_msg('Could not start smstools.service')
			error = True

	if not error:
		sys.exit(0)
	else:
		sys.exit(1)
# END Function

"""
Print Messages to the screen and logfile
"""
def debug_msg_sql(sql, mylist):

	mysql = " - SQL: "+str(sql)
	myvals = " - Values: "+', '.join(map(str,mylist))

	if debug:
		sys.stdout.write(mysql+"\n")
		sys.stdout.write(myvals+"\n")
		sys.stdout.flush()

	logging.debug(mysql)
	logging.debug(myvals)


"""
Print Messages to a File
"""
def save_at_command(mystr):
	if mystr.find('AT+') > -1:
		with open(atfile, "a") as f:
			f.write(mystr+"\n")

"""
Print sent list to a File
"""
def save_send_details(mystr):
	format = "%a %b %d %H:%M:%S"
	d = datetime.datetime.today().strftime(format)
	with open(sendlist, "a") as f:
		f.write(d+" ::: "+mystr+"\n")


"""
Print Messages to a File
"""
def save_date(myfile):
	format = "%a %b %d %H:%M:%S"
	d = datetime.datetime.today().strftime(format)
	with open(myfile, "a") as f:
			f.write("------------------------------\n"+d+"\n------------------------------\n")

"""
Delete Files older than 30 days

Find Files that are older then 10 days
Move those files to the archive path
Delete Files in the achive older than 30 days
"""
def clean_modem_files():

	global modem_files_path
	global modem_file_cutoff_in_days

	debug_msg("Deleting modem temp files more than "+str(modem_file_cutoff_in_days)+" days old")

	now = time.time()
	cutoff = now - (modem_file_cutoff_in_days * 86400)

	files = os.listdir(modem_files_path)
	for xfile in files:
		if os.path.isfile(str(modem_files_path) + xfile):
			t = os.stat(str(modem_files_path) + xfile)
			c = t.st_mtime

			if c < cutoff:
				debug_msg(" - deleting "+str(modem_files_path) + xfile)
				os.remove(str(modem_files_path) + xfile)

#Function Ends Here


"""
Make date as filename
"""
def get_date_as_filename():
	fn = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
	return fn

""" ---------------------------------------------------------

	Serial Communications

--------------------------------------------------------- """

"""
Function to Initialize the Serial Port
"""
def init_serial():

	global ser

	ser = serial.Serial()

	ser.baudrate = args['baudrate']

	# enable hardware control
	ser.rtscts = False
	
	ser.port = args['port']

	#Specify the TimeOut in seconds, so that SerialPort
	#Doesn't hangs
	ser.timeout = 0

	# -----------------------------------
	# Check is the Serial Port is being used 
	# -----------------------------------
	cmd = "sudo lsof | grep "+ser.port

	while True:
		p = subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE)
		line = p.stdout.readline()
		if line:
			msg = 'Serial Port ' + str(ser.port) + ' ' + str(ser.baudrate) + ' is being used'
			debug_msg(msg)
			val = line.split()
			msg = str(val[0].decode("utf-8")) + ' PID: ' + str(val[1].decode("utf-8"))
			debug_msg(msg)

			if 'gammu-sms' in str(val[0].decode("utf-8")):
				debug_msg("Shutting down gammu-smsd...")
				p = subprocess.Popen("sudo systemctl stop gammu-smsd",shell=True,stdout=subprocess.PIPE)
			elif 'smsd' in str(val[0].decode("utf-8")):
				debug_msg("Shutting down smstools...")
				p = subprocess.Popen("sudo systemctl stop smstools",shell=True,stdout=subprocess.PIPE)
			else:
				debug_msg("Trying again in 60 seconds...")
				time.sleep(60)  # Try again in 1 minute

		else:
			msg = 'Serial Port ' + str(ser.port) + ' ' + str(ser.baudrate) + ' seems to be free to use'
			debug_msg(msg)
			ser.open()      #Opens SerialPort
			break

	# print port open or closed
	if ser.is_open:
		debug_msg('Openned: ' + str(ser.name) + ", baud: "+str(ser.baudrate))        # .name is the port connection

#Function Ends Here


"""
Read from the Serial Port
"""
def serial_read(search='OK', mytimeout=2, length=10):
	
	ret = {}
	ret['search'] = search
	ret['read'] = ''
	curr_time = time.time()
	while True:
		holder = ser.read(length)
		ret['read'] += str(holder.decode())
		if search in ret['read']:
			ret['status']="Serial Read Search '"+search+"' Found."
			ret['success']=True
			return ret
		if time.time()-curr_time >= mytimeout:
			ret['status']="Serial Read Search Timed Out."
			ret['success']=False
			return ret



"""
 Edit the MMS Message
 Recipients -> AT+QMMSEDIT=<function>,<option>,<optstring> 
 command('AT+QMMSEDIT=1,1,<optstring>')

Integer type function.
0 - Delete all
1 - Operate “TO address”
2 - Operate “CC address”
3 - Operate “BCC address”
4 - Operate title
5 - Operate file as attachment
Integer type option
0 - Delete the specific setting
1 - Config the specific Setting
String optstring
string - if function is 1,2,3,4 then TO, CC, BCC, Title STRING Address
string - if function is 5 then filename of attachement
		 ie. AT+QMMSEDIT=5,1,"RAM:test_pic.jpg"

Query the setting command('AT+QMMSEDIT=4')
"""
def create_message(recipient, message, images=[], twofactor='', mqttid='', friendlytitle='', title='', altmsg='', img_userpass='', img_delay=0, img_qty=1, img_qty_delay=1):

	global textfile_holder
	global saved_image_files

	details = {}

	if not recipient:
		output_close('create_message: Recipient cannot be empty')
	elif not message and not images:
		output_close('create_message: Both Message and Image cannot be empty')


	# check all phone numbers
	recipient = recipient.strip('\"')
	mobile_list = recipient.split(",")
	
	for temp in mobile_list:
		if len(temp) != 10:
			xtra=". mobile is length "+str(len(temp))
			output_close("Error: Phone number "+temp+" is too long or short"+xtra)

	# Clear all MMS Messages
	clear_entries()

	debug_msg("Creating MMS Message")

	# TO
	# send to one recipient
	rec='1'
	rectext='standard'
	if len(mobile_list) > 1:
		# send to multiple recipeints by BCC
		rec='3'
		rectext='BCC'
		
	for mobile in mobile_list:
		at_command('AT+QMMSEDIT='+rec+',1,"'+mobile+'"') # to phone no.
		debug_msg(' - Added '+rectext+' to send: '+mobile+' ('+mqttid+')')

	details['recipient']=recipient
	details['mobile']=recipient  # this value is used when saving to DB

	# Attach Title
	if title:
		at_command('AT+QMMSEDIT=4,1,"'+title+'"')
		debug_msg(' - Title: '+title)

	details['title']=title

	# Attach Image
	if images:
		details['images']=[]
		for img in images:
			debug_msg(' - Image: '+img)
			debug_msg(' - Image: Delay '+str(img_delay))
			if int(img_delay) > 0:
				debug_msg(' -- delay download: '+img_delay+' secs')
				time.sleep( int(img_delay) )
				debug_msg(' -- continuing')

			for c in range(int(img_qty)):
				
				# clear attachments before uploading first image
				clear_attachments=True
				if images.index(img) > 0:
					clear_attachments=False

				imagefile_holder = upload_file(img, False, clear_attachments, img_userpass, (c+1))
				if not imagefile_holder:
					debug_msg(' -- image was not found')
					if altmsg:
						debug_msg(' -- substituting message with alternate message: '+altmsg)
						message = altmsg
					break
				else:
					saved_image_files.append(imagefile_holder)
					details['images'].append(imagefile_holder)

				if (c+1) < int(img_qty):
					debug_msg(' -- waiting '+str(img_qty_delay)+' secs before next download')
					time.sleep(int(img_qty_delay))

	elif message.lower() == 'ready!':
		debug_msg(' - Substituting Message with Alternate Message: '+altmsg)
		message = altmsg

	if not images:
		details['images']=[]

	# Attach Message
	# we keep the textfile path and name so we can delete later
	# debug_msg(' - Message before make_text_file: '+message)
	if message:
		textfile = make_text_file(urllib.parse.unquote_plus(message))
		textfile_holder = upload_file(textfile, True)

		debug_msg(' - Message: '+message)
		details['message']=message
		details['msg']=urllib.parse.unquote_plus(message)  #for database entry
	else:
		debug_msg(' - Message: none given')
		details['message']='none given'
		details['msg']=details['message']

	if twofactor:
		twofactor=twofactor.replace('"', '')
		twofactor=twofactor.replace('\'', '')
		details['twofactor']=twofactor   # for database entry
	else:
		details['twofactor']=''

	if mqttid:
		debug_msg(' - Mqtt ID: '+mqttid)
		details['mqttid']=mqttid   # for database entry
	else:
		details['mqttid']=''

	if friendlytitle:
		debug_msg(' - Friendly Title: '+friendlytitle)
		details['friendlytitle']=friendlytitle   # for database entry
	else:
		details['friendlytitle']=''

	return details

#Function Ends Here  


"""
Function that writes and reads from serial until timeout occurs.
msg == AT command to execute
timeout == is the time until end execution
ok == is the desired AT print
end == ending ascii character
"""
"""
THIS IS THE OLDER COMMAND THAT DELT WITH TWO TYPES OF MSG
VARS, 1-STRING & 2-LIST
THIS HAS BEEN DISABLED
def command(msg, timeout=2, ok='OK', end=13):

	# if list then break it down. See Array lists at the top os script
	if type(msg) is list:
		#t0 = time.time()
		while True:
			# send the query
			ret = command_str(msg[0], timeout, msg[1], end)

			# if the query response was not found, send set AT command
			if not ret['success']:
				debug_msg("Sending Command: "+msg[2])
				ret = command_str(msg[2], ok='OK')

			return ret

			#if time.time()-t0 >= timeout:
			#    debug_msg("Timeout while executing command: "+msg[0])
			#    return false

	ret = command_str(msg, timeout, ok, end)
	return ret
#Function Ends Here
"""

"""
Write a command to Serial Port
Wait for a response
Check the response
If response is expected return TRUE
If response is abnormal then write command to Serial and recheck it

arg list of dicts
	dicts must have keys, query, expected, correct
"""
def verify_settings(mylist):

	for k0 in mylist:
		for k1, v1 in mylist[k0].items():
			if 'desc' in k1:
				desc = v1
			elif 'query' in k1:
				query = v1
			elif 'expected' in k1:
				expected = v1
			elif 'correct' in k1:
				correct = v1

		debug_msg("Checking:  "+desc)
		debug_msg("- Sending: "+query)
		# save_at_command(msg)
		ser.write(str.encode(query+chr(13)))
		ret = serial_read( 'OK' )

		#debug_msg("\nDEBUG MODE ---- RESPONSE IS SET TO SUCCESS FOR EVERY COMMAND")
		#ret={}
		#ret['success']="success"
		#ret['read']=expected
		
		if not ret['success']:
			debug_msg(" [ FAILED ]")
			debug_msg(" - Response: "+ret['status'])
			debug_msg(" - Answer:   "+ret['read'])
			close_serial_connection()
		if expected not in ret['read']:
			debug_msg(" [ FAILED ]")
			debug_msg(" - Response: "+ret['status'])
			debug_msg(" - Answer:   "+ret['read'])
			if correct:
				debug_msg(" - Setting: "+correct, False)
				ser.write(str.encode(correct+chr(13)))
				ret = serial_read('OK')
				if not ret['success']:
					debug_msg(" [ FAILED ]")
					debug_msg(" - Response: "+ret['status'])
					debug_msg(" - Answer:   "+ret['read'])
					close_serial_connection()
				else:
					debug_msg("\n[ SET OK ]")
			else:
				debug_msg(" - There is no AT correction command. Exiting")
				close_serial_connection()
		else:
			debug_msg(" [  OK  ]")
# Function Ends Here
			


"""    
Same as function command but msg is string
"""
def at_command(msg, ok='OK', timeout=2, length=10):

	try:
		if ser.is_open:
			save_at_command(msg)

			# t0 = time.time()
			#while True:
			ser.write(str.encode(msg+chr(13)))
			ret = serial_read(ok, timeout, length)

			if not ret['success']:
				debug_msg('AT Command Failed: '+msg)
				debug_msg(""+ret['status'])
				debug_msg("Error Code: "+error_code(ret['read']))
				debug_msg("Response: \n"+ret['read'])

			return ret
	except:
		return


# Function Ends Here

"""
Download an image file from the web
"""
def download_image(url, userpass='', imgid=1):
	
	import base64

	global mtype
	global default_img_size

	debug_msg("Analyzing: "+url)

	# make a new filename
	#filename = os.path.basename(urlparse.urlparse(url).path)
	filename = os.path.basename(urllib.parse.urlparse(url).path)

	debug_msg("filename: "+filename)
	
	ext = os.path.splitext(filename)[1]
	debug_msg("extension: "+ext)

	file_noext = os.path.splitext(filename)[0]

	if len(ext) == 0:
		if int(imgid) > 1:
			filename = file_noext+'_'+str(imgid)
		else:
			filename = filename
	else:
		if int(imgid) > 1:
			filename = file_noext+'_'+str(imgid)+ext
		else:
			filename = file_noext+ext


	# if len(base) > 15:
	#     ext = os.path.splitext(base)[1]
	#     time_string = str(int(time.mktime(time.localtime())))
	#     base = (time_string+"_"+str(imgid)+ext).lower()

	#elif len(base) <=15:
	#    ext = os.path.splitext(base)[1]
	#    base = (base+"_"+str(imgid)+ext).lower()

	# if base is empty
	# elif not base:
	#     base = get_date_as_filename()
	#     base = base+"_"+str(imgid)

	myfile = modem_files_path+filename

	debug_msg("Downloading Image: "+url)

	# Some files can't be downloaded without a User-agent Header. We have to make one
	# http://www.hanedanrpg.com/photos/hanedanrpg/14/65194.jpg
	hdr = urllib.request.Request(url, None, {'User-agent' : 'Mozilla/5.0 (Windows; U; Windows NT 5.1; de; rv:1.9.1.5) Gecko/20091102 Firefox/3.5.5'})
	
	if userpass:
		auth=userpass.split(':')
		debug_msg("Using Basic Authentication: User: "+auth[0]+", Pass: "+auth[1])

		inbytes = userpass.encode()
		base64string = base64.b64encode(inbytes)
		hdr.add_header("Authorization", "Basic %s" % base64string)  

	try: 
		imgData = urllib.request.urlopen(hdr, timeout=2).read()

	except urllib3.HTTPError as e:
		extra=''
		if e.code == 401:
			extra='. Http Basic Authentication Failed'
		myerr = 'Error: Downloading Image HTTPError = ' + str(e.code) + extra
		output_close(myerr)

	except urllib3.URLError as e:
		myerr = 'Error: Downloading Image URLError = ' + str(e.reason)
		output_close(myerr)

	except httplib.HTTPException as e:
		myerr = 'Error: Downloading Image HTTPException'
		output_close(myerr)

	except Exception:
		import traceback
		myerr = 'Error: Downloading Image generic exception: ' + traceback.format_exc()
		output_close(myerr)

	debug_msg("Saving file as: "+myfile)
	output = open(myfile,'wb')
	output.write(imgData)
	output.close()

	# check if image downloaded
	img_types = ['image/gif', 'image/jpg', 'image/png', 'image/jpeg']
	mtype = magic.from_file(myfile, mime=True)
	debug_msg("Downloaded image file type: "+ mtype)
	if not mtype in img_types:
		debug_msg("Image type: "+mtype+" is not a valid image type. Aborting.")
		return False

	# check the mime type with the file ext
	mime_ext = mtype.split('/',1)[1]
	myfile_ext = os.path.splitext(myfile)[1]
	myfile_full = os.path.splitext(myfile)[0]
	if mime_ext != myfile_ext:
		if 'jpg' in myfile_ext:
			debug_msg("Mime type jpg is OK as jpeg")
		else:
			debug_msg("Correcting filename with extension: ."+mime_ext)
			newfile = myfile_full+'.'+mime_ext
			debug_msg("New Filename: "+newfile)
			os.rename(myfile, newfile)
			myfile = newfile

	size=int(default_img_size)
	while 'gif' not in myfile_ext:
		s = getFilesize(myfile)
		if s > max_image_filesize:
			debug_msg(" - Size too large, resizing...")
			resize_image(myfile, size)
			size = size - 50
		else:
			break

	return myfile
# Function Ends Here


"""
Check if File exists and return the path to it

arg - string filename ( must be in images filepath)
returns

"""
def verify_filename(myfile):

	# strip all but filename
	myfile = myfile.strip('\"')
	debug_msg("Getting basename from: "+myfile)
	base = os.path.basename(myfile)

	# look for an extention. if none then glob search in image path
	extension = os.path.splitext(base)[1]
	if not extension:
		myfile = imagepath+base+"*"
		debug_msg("Searching for file: "+myfile+" ...")
		result = glob.glob(myfile)
		if result:
			debug_msg(" - Found: "+result[0])
			myfile = result[0]
			base = os.path.basename(myfile)
		else:
			debug_msg(" - Not found")
			return False
	else:
		debug_msg("Searching for filename: "+myfile+"...")
		if not os.path.isfile(myfile):
			debug_msg(" - "+myfile+" does not exist. Searching...")
			debug_msg("Searching for filename: "+base+" ...")
			myfile = modem_files_path+base
			if not os.path.isfile(myfile):
				debug_msg(" - "+myfile+" does not exist. Searching...")
				myfile = imagepath+base
				if not os.path.isfile(myfile):
					debug_msg(" - "+myfile+" does not exist. Searching...")
					myfile = send_bulk_mms_path+base
					if not os.path.isfile(myfile):
						debug_msg(" - "+myfile+" does not exist. Searching...")
						myfile = base
						if not os.path.isfile(myfile):
							debug_msg(" - "+myfile+" does not exist. Exiting")
							output_close(myfile+" does not exist. Exiting")
						
	debug_msg("-  Found "+myfile)

	return myfile

# Function verify_filename Ends Here



"""
Upload a File to RAM

arg - string filename (must be in modem_files_path)
arg - boolean true for ASCII, null or false for binary (ie. jpg)

upload_file('AT+QFUPL="RAM:'+fl+'",'+s+',300,1', connect=fl)
"""
def upload_file(file, ascii=False, clear_attachments=False, img_userpass='', img_id=1):
	
	global default_img_size

	if 'http' in file:
		myfile = download_image(file, img_userpass, img_id)
		if not myfile:
			debug_msg("File: "+file+" could not be downloaded.")
			debug_msg("Check url or check the file in "+modem_files_path+", its a "+str(mtype)+" mime type!")
			close_serial_connection()
	else:
		myfile = file


	myfile = verify_filename(myfile)

	# # strip all but filename
	debug_msg("Getting basename from: "+myfile)
	base = os.path.basename(myfile)

	# # look for an extention. if none then glob search in image path
	# extension = os.path.splitext(base)[1]
	# if not extension:
	#     myfile = imagepath+base+"*"
	#     debug_msg("Searching for file: "+myfile+" ...")
	#     result = glob.glob(myfile)
	#     if result:
	#         debug_msg(" - Found: "+result[0])
	#         myfile = result[0]
	#         base = os.path.basename(myfile)
	#     else:
	#         debug_msg(" - Not found")
	#         return False
	# else:
	#     debug_msg("Searching for filename: "+myfile+"...")
	#     if not os.path.isfile(myfile):
	#         debug_msg(" - "+myfile+" does not exist. Searching...")
	#         debug_msg("Searching for filename: "+base+" ...")
	#         myfile = modem_files_path+base
	#         if not os.path.isfile(myfile):
	#             debug_msg(" - "+myfile+" does not exist. Searching...")
	#             myfile = imagepath+base
	#             if not os.path.isfile(myfile):
	#                 debug_msg(" - "+myfile+" does not exist. Searching...")
	#                 myfile = file
	#                 if not os.path.isfile(myfile):
	#                     debug_msg(" - "+myfile+" does not exist. Exiting")
	#                     return False
						
	#     debug_msg("-  Found "+myfile)

	size_str = str(os.path.getsize(myfile))
  
	if ( size_str == os.path.getsize(myfile) ):
		print ("File "+myfile+" size is zero. Exiting.")
		close_serial_connection()

	size = int(default_img_size)
	myfile_ext = os.path.splitext(myfile)[1]
	resized = False

	while True:
		s = getFilesize(myfile)
		size_str = str(s)

		# set the maximum image file size allowed
		#if 'gif' in myfile_ext:
		#	max_size = max_gif_size
		#else:
		#max_size = max_image_filesize

		if s > max_image_filesize:
			if 'gif' not in myfile_ext:
				debug_msg(" - "+myfile_ext+" image size too large, resizing...")
				resize_image(myfile, size)
				size = size - 50
				resized = True
			else:
				resized = True
				break
		else:
			break

	if resized:
		size_str = str(os.path.getsize(myfile))

	# attach the text file
	if ascii:
		verify_settings(char_ascii)

	"""
	Read the Binary/Ascii File in to memory
	"""
	with open(myfile, "rb") as binary_file:
		# Read the whole file at once
		data = binary_file.read()
		#print(data)


	"""
	AT+QFUPL="RAM:test_mms.txt",100,300,1
		100 - the maximum size of file in bytes
		300 - indicates timeout value
		1 - indicates ACK mode.
	"""
	count=1
	while True:
		upl='AT+QFUPL="RAM:'+base+'",'+size_str+',300,1'
		debug_msg("Uploading into modem RAM: "+base)
		ret = at_command(upl, ok='CONNECT')

		if not ret['success']:
			if '407' not in ret['read']:
				close_serial_connection()
			elif count > 2:
				debug_msg("Could not Upload after 2 tries")
				clear_ram()
				close_serial_connection()
			else:
				debug_msg("Deleting File and trying Again...")
				clear_ram()
				count+=1
		else:
			break

	# Send the Binary/Text data
	ser.write(data)
	ret = serial_read('OK')

	if size_str in ret['read']:
		#debug_msg(ret)
		debug_msg(" - Uploaded "+size_str+" bytes to RAM")

		# Clear all Attachments before adding to MSG Query
		if clear_attachments:
			debug_msg(" - Clearing query attachments before adding new one")
			at_command('AT+QMMSEDIT=5,0')

		# Attach the File to query
		at_command('AT+QMMSEDIT=5,1,"RAM:'+base+'"')
		# Query the attachment
		result = at_command('AT+QMMSEDIT=5')
		if result['success']:
			mylist = search_string(result['read'], '+QMMSEDIT: 5')
			for ln in mylist:
				debug_msg(ln)
		else:
			debug_msg("Nothing was uploaded. Check Logs")

		return myfile
	else:
		debug_msg(ret['read'])
		return False
# Function ends here


"""
Get the size of a file
"""
def getFilesize( myfile='' ):

	if not os.path.isfile(myfile):
		debug_msg("File: "+myfile+" does not exist")
		close_serial_connection()

	size = os.path.getsize(myfile)
	sizestr = humanfriendly.format_size(size)
	debug_msg(" - Size: "+str(size)+" bytes or "+sizestr)
	
	return size
# Function Ends Here

"""
Clear Ram and Querys
"""
def clear_all():

	clear_ram()
	clear_entries()
# End Function Here

"""
Clear RAM
"""
def clear_ram(check=False):

	if check:
		tries = 0
		while True:
			l = at_command('AT+QFLST="RAM:*"', 'OK', 5)
			if l is None:
				debug_msg("AT+QFLST=\"RAM:*\" returned an empty value")
				from pprint import pprint
				#pprint(globals())
				pprint(locals())
				#print vars(l)
				ser.close() 
				sys.exit()
			nlines = l['read'].count('\n')
			debug_msg("RAM files found in memory: "+str(nlines))
			if nlines > 2:
				if ( tries > 2 ):
					debug_msg(" - Cannot Delete RAM.")
					debug_msg(" - Powering down Cellular Modem normally")
					at_command('AT+QPOWD=1', 'OK', 10)
					debug_msg(" - Rebooting RPi4 in 1 minute")
					rc = subprocess.call("shutdown -r +1", shell=True)
					ser.close()
					sys.exit()

				debug_msg(" - Deleting RAM one-by-one")
				filescount = 0
				tries += 1
				ll = l['read'].splitlines()
				for aline in ll[:]:
					if '+QFLST:' in aline:
						filen = re.findall(r'"RAM:(.+?)"',aline)
						debug_msg("  "+str(filescount+1)+" DEL: "+str(filen[0]))
						at_command('AT+QFDEL="RAM:'+str(filen[0])+'"', 'OK', 10)
						filescount += 1

			else:
				break

	else:     
		# Clear the RAM
		at_command('AT+QFDEL="RAM:*"', 'OK', 5)

# End Function Here

"""
Clear Entrys
"""
def clear_entries():
	
	# Clear all querys
	at_command('AT+QMMSEDIT=0')
# End Function Here


"""
Look up an error code in a file list and display description
"""
def error_code(mystr):

	global errorcodes

	if not errorcodes: 
		if not os.path.isfile(errorCodesFile):
			debug_msg(" - File: "+errorCodesFile+" does not exist")
			close_serial_connection()

		with open(errorCodesFile, 'r') as f:
			errorcodes = ast.literal_eval(f.read())

	txt = mystr.split('\n')
	for line in txt:
		if 'ERROR' and re.findall('\d+',line):
			#debug_msg("Error Found: "+line)
			err=re.findall('\d+',line)
			for key,value in errorcodes: 
				if key in err:
					return value
					break
	return "(unknown)"
#Function Ends Here


"""
Look for Lines in string and print them
"""
def search_string(mystring, mysearch):

	results=[]
	txt = mystring.split('\n')
	for line in txt:
		if mysearch in line:
			results.append(line)

	if not len(results):
		return False

	return results


"""
Make a text file from a string
"""
def make_text_file(mystr):

	time_string = str(int(time.mktime(time.localtime())))
	fn = modem_files_path+time_string+'.txt'
	f = open(fn, 'w+')
	#debug_msg("make_text_file: Making Message text File: "+mystr)
	f.write(str(mystr.replace('\\n', '\n')))
	f.close

	if not os.path.isfile(fn):
		debug_msg("Error: "+fn+" could not be created")
		close_serial_connection()

	debug_msg("Created Msg Text File: "+fn)

	return fn
#Function Ends Here

"""
Delete a Files in list

 - Only delete files in the modem_files_path. Images from another location
	should not be deleted
"""
def delete_images(imglist):

	status=True

	if not args['imgnodelete']:
		for x in imglist:

			#if file exists, delete it
			if os.path.isfile(x):
				## try to delete file ##
				try:
					os.remove(x)
				except OSError as e:  ## if failed, report it back to the user ##
					debug_msg("Error: %s - %s." % (e.filename,e.strerror))
					status=False

				debug_msg("Deleted: "+x)
	
	return status
#Function Ends Here

"""
Send Message
"""
def send_message(details):
 
	recid = table('delete', {'days':30})
	recid = table('insert', details)
	details['id'] = recid
	details['sent']=0
	details['tries']=0

	count=1

	while True:
		debug_msg("Trying to Send MMS (attempts: "+str(count)+")")
		result = at_command('AT+QMMSEND=20', '+QMMSEND: 0,200')

		if not result['success']:
			debug_msg(" - Send Message FAILED")

			if count > 3:
				debug_msg(" - Attempted 3 times... Aborting.")
				return False
			else:
				count += 1
				details['tries'] = count
				#table('update', details)
		else:
			debug_msg(" - Success")
			details['sent'] = 1
			#table('update', details)
			return True

# Function Ends Here


"""
Close and end program
"""
def close_serial_connection():
	
	global textfile_holder
	global saved_image_files

	close_db_connection()

	debug_msg('Clearing RAM & Entries...')
	clear_all()

	debug_msg('Closing Connection...')
	try:
		if ser.is_open:  
			ser.close()   # close serial port
			if ser.is_open:
				debug_msg(' - Failed')
		else:
			debug_msg(' - Not open, therefore close not neccessary')

		if len(saved_image_files) > 0:
			#debug_msg("Deleting Image File...")
			delete_images(saved_image_files)

		clean_modem_files()
		
	except:
		debug_msg('Connection not open.')

	debug_msg('Done.')

	#sys.exit()    # exit program is done in output_close()
#Function Ends Here



"""
----------------------------------------------------------

	MEAT AND POTATOES

----------------------------------------------------------
"""

if not database_reachable:
	debug_msg("** Could not connect to Database: "+DBFILE+" **")

"""
Usage
"""
s="""
Files
-----
		Log File:       {log}
		Quectel E25 Chipset Error Codes:
						{error}
Note
----
		If Title(-s) and File(-i) are not supplied
		then SMS Message will be used to send

		All sent messages are save to a sqlite3 database
		Filename:       {db}
Author
------
		Michael Connors
		daddyfix@outlook.com
				
""".format( log=logfile,
			error=errorCodesFile,
			db=DBFILE
)
parser = argparse.ArgumentParser(
				description='Script to send MMS/SMS Messages to one or more recipients',
				formatter_class=argparse.RawTextHelpFormatter,
				epilog=(s)
)

#----------------------------------------------------------
# Group args as optional but One must be selected
#-----------------------------------------------------------
send_help = """

Send MMS Message OPTIONS
------------------------

"""
recipient_help = """** Required **
Recipient Phone Number (ie. 1705-999-1111).
This can be repeated multiple times
"""

message_help = """** Required if No Image supplied**
Attach text to MMS message
Message can have line feed with \\n"""

twofactor_help = """** NOT Required **
Add a secret phrase or 4 digit number that the reciever
reponds to for a two-factor authenication check.\\n"""
#-----------------------------------------------------------
# Regular Args
#-----------------------------------------------------------
parser.add_argument('-r','--recipient', help=recipient_help, required=False)
parser.add_argument('-m','--message', help=message_help, required=False)
parser.add_argument('-s','--title', help='Attach a title to the MMS Message', required=False)
parser.add_argument('-i','--image', dest='images', action='append', help='Attach one or more image files (ie .jpg .png .gif) or Url to Image', required=False)
parser.add_argument('-t','--twofactor', help=twofactor_help, required=False)
parser.add_argument('-z','--imgresize', help='Resize while maintaining aspect ratio and exit. Give one integer. So, 300 = 300x300', required=False)
parser.add_argument('--mqttid', help='The recipients MQTT ID (used in logs)', required=False)
parser.add_argument('--friendlytitle', help='A text friendly title of the media (used in logs)', required=False)
parser.add_argument('--imguserpass', help='Basic Http Authentication for Image URL. Format <username>:<password>', required=False)
parser.add_argument('--imgdelay', help='Delay in seconds before downloading image from url. Default: '+default_img_delay+' secs', required=False)
parser.add_argument('--imgqty', help='Number of image calls made to image url. Default: '+default_img_qty, required=False)
parser.add_argument('--imgqtydelay', help='Time in seconds between each image download. Default: '+default_img_qty_delay+' secs', required=False)
parser.add_argument('-x','--imgnodelete', action='store_true', help='Do not delete the image file from disk. Default: Delete Image', required=False)
parser.add_argument('-a','--altmsg', help='Alterntive message if image name was given and can not be found', required=False)
mystr="""
Default File Path: {files}
Image File Path: {images}
Files must be in either of the above directories
unless otherwise specified.
""".format(files=modem_files_path,
		   images=imagepath
)
#parser.add_argument('-S','--readall', action='store_true', help="Read all the SMS messages recieved", required=False)
parser.add_argument('-p','--path', help=mystr, required=False)
parser.add_argument('-b','--baudrate', help='Default: '+default_baudrate, required=False)
parser.add_argument('-o','--port', help='Default: '+default_port, required=False)
parser.add_argument('-d','--debug', action='store_true', help='Default: '+str(debug), required=False)
parser.add_argument('--atcmd', help='Send an AT COMMAND to the gsm modem and display the response', required=False)
parser.add_argument('--json', action='store_true', help='Output results as json [Default]', required=False)
parser.add_argument('--text', action='store_true', help='Output results as text', required=False)
parser.add_argument('--output', help='json or text. Default: '+default_output, required=False)

# Add all the Command Line args to array(list)
args = vars(parser.parse_args())

if 'message' not in args.keys():
	if 'image' not in args.keys():
		parser.print_help()
		sys.exit()

# set the defaults
if not args['baudrate']:
	args['baudrate'] = default_baudrate
if not args['port']:
	args['port'] = default_port
if not args['text'] and not args['json']:
	args['json'] = True
if args['debug']:
	debug = True
if args['atcmd']:
	debug = True
	custom_at_command = True
if not args['mqttid']:
	args['mqttid'] = default_mqttid
if not args['friendlytitle']:
	args['friendlytitle'] = default_friendlytitle
if not args['imgnodelete']:
	args['imgnodelete'] = default_img_no_delete
else:
	args['imgnodelete'] = True
#if not args['imgresize']:
#	args['imgresize'] = default_img_size
if not args['imgdelay']:
	args['imgdelay'] = default_img_delay
if not args['imgqty']:
	args['imgqty'] = default_img_qty
if not args['imgqtydelay']:
	args['imgqtydelay'] = default_img_qty_delay
if args['output']:
	if (args['output'].find('json') != -1):
		args['json'] = True
	elif (args['output'].find('text') != -1):
		args['json'] = False
	else:
		debug_msg( "--output arg ("+args['output']+") is not recognized. Choose 'json' or 'text'" )
		sys.exit()



"""
Save Date to Files
"""
save_date(logfile)
save_date(atfile)

# ---------------------------- START ----------------------------

"""

Resize the Image if requested and Exit

"""
if args['images']:
	if args['imgresize']:
		myfile = verify_filename(args['images'][0])
		if not myfile:
			msg = "Error Verifying Image File: "+args['images'][0]+" ***"
			debug_msg(msg)
			output_close(msg)

		size_before = size_after = getFilesize( myfile )
		size_before_str = size_after_str = humanfriendly.format_size(size_before)
		size = int(args['imgresize'])
		while True:
			if size_after > 200000:
				debug_msg(" - Size too large, resizing to "+str(size)+'x'+str(size))
				resize_image(myfile,size)
				size = size - 50
				size_after = getFilesize( myfile )
				size_after_str = humanfriendly.format_size(size_after)
			else:
				break
		
		output_close("Original size: "+size_before_str+". After Resize: "+size_after_str)


"""

Call the Serial Initilization

"""
init_serial()

"""

Check Connection Params

"""
verify_settings(modem)
verify_settings(char_ascii)
clear_ram(True)

debug_msg( "Args Given: "+str(args)[1:-1] )

"""

Send an AT COMMAND to the gsm modem

"""
if custom_at_command:
	ret = at_command( args['atcmd'] )
	output_close(ret)


"""

Create a Message and Send 

"""
details_dict = create_message(args['recipient'], args['message'], args['images'], args['twofactor'], args['mqttid'], args['friendlytitle'], args['title'], args['altmsg'], args['imguserpass'], args['imgdelay'], args['imgqty'], args['imgqtydelay'])

status = send_message(details_dict)

if not status:
	msg = "Error Sending Message: "+status+" ***"
	debug_msg(msg)
	output_close(msg)
	
else:
	msg = "Sent OK"
	debug_msg(msg)

	# Add an entry to the sent messages list file
	if args['message'] is None:
		message='empty'
	else:
		message = urllib.parse.unquote_plus(args['message'])

	if args['images']:
		if args['altmsg']:
			message = args['altmsg']

	mqtttmp = '(unknown)'
	if args['mqttid']:
		mqtttmp = '('+args['mqttid']+')'

	# if the message has an imdb link (Click for Details) then substitute with friendly title
	if args['friendlytitle'] and 'Click' in message:
		message = args['friendlytitle']+' (with IMDB link)'

	senddetails = args['recipient']+' '+mqtttmp+" -> "+message
	save_send_details(senddetails)
	output_close(msg)
