# encoding: utf-8
"""
http.py

Created by Thomas Mangin on 2014-02-06.
Copyright (c) 2014-2014 Exa Networks. All rights reserved.
"""

import os
import sys
import urlparse
import SimpleHTTPServer
import SocketServer
import json
import socket

from .log import log,err

# ugly but practical for testing ..
if __name__ != '__main__':
	from .thread import Thread

def nop (arg):
	return arg

# def snmp_json (data):
# 	s = {}
# 	for link,information in data.iteritems():
# 		s.setdefault(information['ifHCInUcastPkts'] + information['ifInNUcastPkts'],[]).append(link)

# 	display = sorted(s.keys())
# 	display.reverse()
# 	r = []
# 	for speed in display:
# 		links = s[speed]
# 		for link in sorted(links):
# 			d = {'link':link}
# 			information = data[link]
# 			for k,v in information.iteritems():
# 				d[k] = v
# 			r.append(d)
# 	return json.dumps(r)

# def flow_overall (data):
# 	r = {}
# 	for proto in data:
# 		for counter in data[proto]:
# 			r["%s_%s" % (proto,counter)] = data[proto][counter]
# 	return json.dumps(r)


def flow_traffic (data):
	nb_keeping = 5

	default = {
		'sipv4' : "127.0.0.1",
		'dipv4' : "127.0.0.1",
		'sport' : "0",
		'dport' : "0",
	}

	best = {}
	maximum = {}
	for direction in ('sipv4','dipv4','sport','dport'):
		for counter in ('bytes','pckts','flows'):
			best['%s_%s' % (direction,counter)] = {-1:[default[direction],]}
			maximum['%s_%s' % (direction,counter)] = [-1,] * nb_keeping

	for t in data:
		for d in data[t]:
			for c in data[t][d]:
				info = data[t][d][c]
				index = '%s_%s' % (d,c)
				for key in info:
					number,minute = key
					if number >= maximum[index][0]:
						best[index].setdefault(number,[]).append(info[key])
						maximum[index] = sorted(maximum[index][1:]+[number,])

	# from pprint import pprint
	# print
	# pprint(best)
	# print

	r = {}
	for direction in ('sipv4','dipv4','sport','dport'):
		r[direction] = {}
		for counter in ('bytes','pckts','flows'):
			index = '%s_%s' % (direction,counter)
			v = {}

			for number in reversed(maximum[index]):
				for key in set(best[index][number]):
					v[key] = v.get(key,0) + number

			l = []
			for key,value in v.iteritems():
				if value > 0:
					l.append({'key': key, 'value': str(value)})

			# XXX: This is really some code to fix the HTML
			for _ in range(max(0,nb_keeping - len(l))):
				l.append({'key': '', 'value' : ''})

			r[direction][counter] = l[:nb_keeping]

	return json.dumps(r)

def json_index (data):
	return """
<html>
	<head></head>
		%s
	<body></body>
</html>
""" % '</br>\n'.join(['<a href="%s" target="%s">%s</a>' % (path,path,path) for path in data])

class HTTPHandler (SimpleHTTPServer.SimpleHTTPRequestHandler):
	# webroot is added to this class
	# snmp is added to this class
	# flow is added to this class

	# monkey patching 3.3 fix http://hg.python.org/cpython/rev/7e5d7ef4634d
	def finish (self):
		try:
			SimpleHTTPServer.SimpleHTTPRequestHandler.finish(self)
		except socket.error:
			# should really check it is really ECONNABORTED
			pass

	def __init__ (self,*args,**kargs):
		self._json = {
			"/json.html"                         : ( 'text/html', json_index,     self.json_list,         () ),
			"/json/"                             : ( 'text/html', json_index,     self.json_list,         () ),
			"/json/snmp/interfaces.json"         : ( 'text/json', json.dumps,     self.snmp.data,         () ),
			"/json/flow/overview.json"           : ( 'text/json', json.dumps,     self.flow.overall,      () ),
			"/json/flow/talkers.json"            : ( 'text/json', flow_traffic,   self.flow.traffic,      () ),
		}
		try:
			SimpleHTTPServer.SimpleHTTPRequestHandler.__init__(self,*args,**kargs)
		except socket.error:
			# should really check it is really ECONNABORTED
			pass

	def json_list (self):
		r = []
		for name in self._json:
			r.append(name)
		return r

	def log_message (*args):
		pass

	def valid_path (self,path):
		for letter in path:
			if letter.isalnum():
				continue
			if letter in ('-','_','.','/'):
				continue
			return False

		return '..' not in path

	def do_HEAD(self):
		self.send_response(200)
		self.send_header('Content-type', 'text/html')
		self.end_headers()
		return

	def do_GET (self):
		content = ''
		fname = ''

		# Parse query data to find out what was requested
		parsedParams = urlparse.urlparse(self.path)
		path = parsedParams.path

		if path.startswith('/json/'):
			code = 200

			if path in self._json:
				encoding, presentation, source, param = self._json[path]
				content = presentation(source(),*param)
			else:
				code = 404
				encoding = 'text/html'
				content = '404'

			if code == 404:
				err('http server could not serve json %s' % path)

		elif self.valid_path(path):
			if path == '/':
				path = '/index.html'
			code = 200
			if path.endswith('.js'):
				encoding = 'application/x-javascript'
			elif path.endswith('.html'):
				encoding = 'text/html'
			elif path.endswith('.css'):
				encoding = 'text/css'
			elif path.endswith(('.jpg','.jpeg')):
				encoding = 'image/jpeg'
			elif path.endswith('.png'):
				encoding = 'image/png'
			elif path.endswith('.gif'):
				encoding = 'image/gif'
			else:
				encoding = 'text/plain'
			fname = os.path.join(self.webroot,path.lstrip('/'))

			if fname and os.path.isfile(fname):
				try:
					with open(fname,'r') as f:
						content = f.read()
				except Exception:
					code = 500
					encoding = 'text/html'
					content = 'could not read the file'
			else:
				code = 404
				encoding = 'text/html'
				content = '404'

			if code == 404:
				err('http server could not serve path %s -> %s' % (path, fname))

		else:
			code = 404
			encoding = 'text/html'
			content = '404'

		self.send_response(code)
		self.send_header('Content-type', encoding)
		self.end_headers()
		self.wfile.write(content)

		return

	def do_POST (self):
		# Parse query data to find out what was requested
		parsedParams = urlparse.urlparse(self.path)
		path = parsedParams.path

		if path == '/post/monitor/ip':
			import cgi
			form = cgi.FieldStorage(
				fp=self.rfile,
				headers=self.headers,
				environ={'REQUEST_METHOD':'POST',
				'CONTENT_TYPE':self.headers['Content-Type'],
			})

			ip = form.getfirst('ip','')
			number = long(ip) if ip and ip.isdigit() else 0

			if number and number < (224 << 24) - 1:  # last unicast IP
				self.flow.monitor(number)
				self.send_response(200)
				self.send_header('Content-type','text/json')
				self.end_headers()
				self.wfile.write(json.dumps(self.flow.monitor_data(number)))
				return

		self.send_response(404)
		self.end_headers()


class _HTTPServerFactory (object):
	use_thread = True

	def __init__ (self,host,port,raising):
		log('http server on %s:%d' % (host,port))
		self.httpd = None
		self.raising = raising

		self.host = host
		self.port = port

	def serve (self):
		SocketServer.TCPServer.allow_reuse_address = True
		server = SocketServer.TCPServer((self.host, self.port),HTTPHandler)
		server.serve_forever()

	def start (self):
		log('starting http server')
		if self.use_thread:
			self.httpd = Thread(self.serve,self.raising)
			self.httpd.daemon = True
			self.httpd.start()
		else:
			self.serve()

	def join (self):
		if self.httpd:
			self.httpd.join(0.1)


class HTTPServer (object):
	servers = {}

	def __init__ (self,configuration,snmp,flow):
		HTTPHandler.webroot = configuration.location.html
		# This will be shared among all instrance
		HTTPHandler.snmp = snmp
		HTTPHandler.flow = flow

	def add (self,host,port,raising):
		key = '%s:%d' % (host,port)
		if key not in self.servers:
			server = _HTTPServerFactory(host,port,raising)
			server.parent = self
			self.servers[key] = server

	def run (self,daemon):
		for key in self.servers:
			if daemon and self.servers[key].use_thread:
				self.servers[key].start()
			if not daemon and not self.servers[key].use_thread:
				self.servers[key].start()

	def join (self):
		for key in self.servers:
			self.servers[key].join()

	def alive (self):
		for key in self.servers:
			if self.servers[key].httpd.isAlive():
				return True
		return False


if __name__ == '__main__':
	one={23200748: {'dipv4': {'pckts': {(5300, 23200749): 1490932248, (-1, 23200748): 2130706433, (103, 23200750): 1390085485, (107, 23200753): 1390092013, (19561, 23200752): 1490932231}, 'bytes': {(720, 23200753): 1390129370, (-1, 23200748): 2130706433, (56647, 23200750): 1490932238, (409776, 23200752): 1390085475, (28836876, 23200749): 1490932231}, 'flows': {(11, 23200752): 1490932234, (-1, 23200748): 2130706433, (7, 23200750): 1390085151, (43, 23200753): 1490932240, (69, 23200749): 1390085144}}, 'sipv4': {'pckts': {(725, 23200750): 1390093537, (-1, 23200748): 2130706433, (43, 23200753): 3331355530, (15664, 23200752): 1390092013, (7, 23200751): 1490932229}, 'bytes': {(58138, 23200751): 1490932242, (-1, 23200748): 2130706433, (6312366, 23200753): 1490932234, (890, 23200750): 3163192613, (2978981, 23200752): 2439115988}, 'flows': {(16, 23200753): 1390085144, (-1, 23200748): 2130706433, (7, 23200750): 1490932239, (15, 23200749): 1390085150, (35, 23200751): 134744072}}}, 4: {'dipv4': {'pckts': {(-1, 4): 2130706433, (-3, 4): 2130706433, (-4, 4): 2130706433, (-5, 4): 2130706433, (-2, 4): 2130706433}, 'bytes': {(-1, 4): 2130706433, (-3, 4): 2130706433, (-4, 4): 2130706433, (-5, 4): 2130706433, (-2, 4): 2130706433}, 'flows': {(-1, 4): 2130706433, (-3, 4): 2130706433, (-4, 4): 2130706433, (-5, 4): 2130706433, (-2, 4): 2130706433}}, 'sipv4': {'pckts': {(-1, 4): 2130706433, (-3, 4): 2130706433, (-4, 4): 2130706433, (-5, 4): 2130706433, (-2, 4): 2130706433}, 'bytes': {(-1, 4): 2130706433, (-3, 4): 2130706433, (-4, 4): 2130706433, (-5, 4): 2130706433, (-2, 4): 2130706433}, 'flows': {(-1, 4): 2130706433, (-3, 4): 2130706433, (-4, 4): 2130706433, (-5, 4): 2130706433, (-2, 4): 2130706433}}}, 23200749: {'dipv4': {'pckts': {(12565, 23200750): 1490932239, (9, 23200749): 1490932241, (281, 23200752): 1490932237, (6, 23200754): 1490932233, (9596, 23200751): 1490932229}, 'bytes': {(18710183, 23200750): 1490932239, (10659, 23200751): 1490932243, (3795, 23200754): 1159668081, (415976, 23200749): 1390085658, (14105, 23200753): 1490932248}, 'flows': {(17, 23200754): 1490932243, (3, 23200751): 1490932234, (18, 23200749): 1490932233, (43, 23200753): 1490932249, (89, 23200752): 1490932242}}, 'sipv4': {'pckts': {(41, 23200749): 520834244, (391, 23200750): 1390087841, (4747, 23200753): 1249759509, (14, 23200752): 1490932238, (7975, 23200754): 34911506}, 'bytes': {(10659, 23200751): 3245197261, (546951, 23200750): 1390087841, (311439, 23200749): 1490932245, (613, 23200752): 520838772, (11954818, 23200754): 34911506}, 'flows': {(3, 23200751): 1490932245, (16, 23200752): 1390085144, (8, 23200749): 1490932238, (65, 23200750): 1490932239, (2, 23200754): 1490932240}}}, 23200750: {'dipv4': {'pckts': {(4541, 23200753): 1490932237, (1081, 23200752): 35009072, (4610, 23200750): 1490932231, (157, 23200754): 1490932233, (7, 23200751): 1490932248}, 'bytes': {(92806, 23200755): 1490932242, (11062357, 23200750): 1490932239, (198796, 23200751): 1490932236, (3942, 23200754): 34616858, (6844578, 23200753): 1490932231}, 'flows':{(11, 23200752): 1490932234, (3, 23200751): 1490932241, (14, 23200753): 1490932240, (26, 23200750): 1490932243, (166, 23200754): 1490932233}}, 'sipv4': {'pckts': {(784, 23200753): 1490932229, (4542, 23200755): 389939994, (6, 23200754): 1844882381, (7, 23200751): 3245197133, (-5, 23200750): 2130706433}, 'bytes': {(3709, 23200753): 1490932241, (878936, 23200755): 1156064098, (3942, 23200754): 1490932236, (1399, 23200752): 520838764, (6811172, 23200751): 389939994}, 'flows': {(6, 23200755): 3163192613, (3, 23200751): 1844846946, (25, 23200752): 1390085144, (11, 23200753): 1490932239, (67, 23200750): 2990491714}}}, 23200751: {'dipv4': {'pckts': {(3667, 23200754): 625850440, (25, 23200752): 1390091821, (-2, 23200751): 2130706433, (2, 23200756): 3639549972, (10, 23200753): 1390085476}, 'bytes': {(40272, 23200753): 1390085485, (159626, 23200752): 625850440, (117, 23200756): 3639549972, (-2, 23200751): 2130706433, (728, 23200754): 1390087394}, 'flows': {(3, 23200756): 1390087985, (1, 23200752): 831557494, (3, 23200753): 1490932233, (-2, 23200751): 2130706433, (2, 23200754): 2915181193}}, 'sipv4': {'pckts': {(25, 23200752): 3651343655, (-2, 23200751): 2130706433, (3667, 23200754): 1390127411, (10, 23200753): 1796712159, (93, 23200755): 2915181215}, 'bytes': {(19613, 23200753): 390746172, (117, 23200756): 1390134674, (40272, 23200752): 1122534314, (-2, 23200751): 2130706433, (159626, 23200754): 1390127411}, 'flows': {(2, 23200755): 134743044, (1, 23200752): 1390132074, (-2, 23200751): 2130706433, (1, 23200753): 1390085145, (2, 23200754): 3475948033}}}}
	two={0: {'dipv4': {'pckts': {(-5, 0): 2130706433, (-2, 0): 2130706433, (-1, 0): 2130706433, (-3, 0): 2130706433, (-4, 0): 2130706433}, 'bytes': {(-5, 0): 2130706433, (-2, 0): 2130706433, (-1, 0): 2130706433, (-3, 0): 2130706433, (-4, 0): 2130706433}, 'flows': {(-5, 0): 2130706433, (-2, 0): 2130706433, (-1, 0): 2130706433, (-3, 0): 2130706433, (-4, 0): 2130706433}}, 'sipv4': {'pckts': {(-5, 0): 2130706433, (-2, 0): 2130706433, (-1, 0): 2130706433, (-3, 0): 2130706433, (-4, 0): 2130706433}, 'bytes': {(-5, 0): 2130706433, (-2, 0): 2130706433, (-1, 0): 2130706433, (-3, 0): 2130706433, (-4, 0): 2130706433}, 'flows': {(-5, 0): 2130706433, (-2, 0): 2130706433, (-1, 0): 2130706433, (-3, 0): 2130706433, (-4, 0): 2130706433}}}, 1: {'dipv4': {'pckts': {(-3, 1): 2130706433, (-1, 1): 2130706433, (-5, 1): 2130706433, (-4, 1): 2130706433, (-2, 1): 2130706433}, 'bytes': {(-3, 1): 2130706433, (-1, 1): 2130706433, (-5, 1): 2130706433, (-4, 1): 2130706433, (-2, 1): 2130706433}, 'flows': {(-3, 1): 2130706433, (-1, 1): 2130706433, (-5, 1): 2130706433, (-4, 1): 2130706433, (-2, 1): 2130706433}}, 'sipv4': {'pckts': {(-3, 1): 2130706433, (-1, 1): 2130706433, (-5, 1): 2130706433, (-4, 1): 2130706433, (-2, 1): 2130706433}, 'bytes': {(-3, 1): 2130706433, (-1, 1): 2130706433, (-5, 1): 2130706433, (-4, 1): 2130706433, (-2, 1): 2130706433}, 'flows': {(-3, 1): 2130706433, (-1, 1): 2130706433, (-5, 1): 2130706433, (-4, 1): 2130706433, (-2, 1): 2130706433}}}, 2: {'dipv4': {'pckts': {(-4, 2): 2130706433, (-5, 2): 2130706433, (-1, 2): 2130706433, (-3, 2): 2130706433, (-2, 2): 2130706433}, 'bytes': {(-4, 2): 2130706433, (-5, 2): 2130706433, (-1, 2): 2130706433, (-3, 2): 2130706433, (-2, 2): 2130706433}, 'flows': {(-4, 2): 2130706433, (-5, 2): 2130706433, (-1, 2): 2130706433, (-3, 2): 2130706433, (-2, 2): 2130706433}}, 'sipv4': {'pckts': {(-4, 2): 2130706433, (-5, 2): 2130706433, (-1, 2): 2130706433, (-3, 2): 2130706433, (-2, 2): 2130706433}, 'bytes': {(-4, 2): 2130706433, (-5, 2): 2130706433, (-1, 2): 2130706433, (-3, 2): 2130706433, (-2, 2): 2130706433}, 'flows': {(-4, 2): 2130706433, (-5, 2): 2130706433, (-1, 2): 2130706433, (-3, 2): 2130706433, (-2, 2): 2130706433}}}, 3: {'dipv4': {'pckts': {(-1, 3): 2130706433, (-2, 3): 2130706433, (-5, 3): 2130706433, (-4, 3): 2130706433, (-3, 3): 2130706433}, 'bytes': {(-1, 3): 2130706433, (-2, 3): 2130706433, (-5, 3): 2130706433, (-4, 3): 2130706433, (-3, 3): 2130706433}, 'flows': {(-1, 3): 2130706433, (-2, 3): 2130706433, (-5, 3): 2130706433, (-4, 3): 2130706433, (-3, 3): 2130706433}}, 'sipv4': {'pckts': {(-1, 3): 2130706433, (-2, 3): 2130706433, (-5, 3): 2130706433, (-4, 3): 2130706433, (-3, 3): 2130706433}, 'bytes': {(-1, 3): 2130706433, (-2, 3): 2130706433, (-5, 3): 2130706433, (-4, 3): 2130706433, (-3, 3): 2130706433}, 'flows': {(-1, 3): 2130706433, (-2, 3): 2130706433, (-5, 3): 2130706433, (-4, 3): 2130706433, (-3, 3): 2130706433}}}, 4: {'dipv4': {'pckts': {(-1, 4): 2130706433, (-3, 4): 2130706433, (-4, 4): 2130706433, (-5, 4): 2130706433, (-2, 4): 2130706433}, 'bytes': {(-1, 4): 2130706433, (-3, 4): 2130706433, (-4, 4): 2130706433, (-5, 4): 2130706433, (-2, 4): 2130706433}, 'flows': {(-1, 4): 2130706433, (-3, 4): 2130706433, (-4, 4): 2130706433, (-5, 4): 2130706433, (-2, 4): 2130706433}}, 'sipv4': {'pckts': {(-1, 4): 2130706433, (-3, 4): 2130706433, (-4, 4): 2130706433, (-5, 4): 2130706433, (-2, 4): 2130706433}, 'bytes': {(-1, 4): 2130706433, (-3, 4): 2130706433, (-4, 4): 2130706433, (-5, 4): 2130706433, (-2, 4): 2130706433}, 'flows': {(-1, 4): 2130706433, (-3, 4): 2130706433, (-4, 4): 2130706433, (-5, 4): 2130706433, (-2, 4): 2130706433}}}}
	for data in (one,two):
		print flow_traffic(data)
