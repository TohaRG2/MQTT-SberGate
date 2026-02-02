import json
import os
import sys
import threading
import re
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer
from logger import log
import sber_api

MIME_TYPES = {
    ".html": "text/html",
    ".js": "text/javascript",
    ".css": "text/css",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".json": "application/json",
    ".ico": "image/vnd.microsoft.icon",
    ".log": "application/octet-stream",
    "default": "text/plain"
}

# Базовая директория приложения для корректного поиска статических файлов
APP_DIR = os.path.dirname(os.path.abspath(__file__))

STATIC_ROUTES = {
    '/SberGate.log': 'SberGate.log',
    '/': 'ui2/index.html',
    '/ui2/main.js': 'ui2/main.js',
    '/ui2/main.css': 'ui2/main.css',
    '/favicon.ico': 'ui2/favicon.ico',
    '/index.html': 'ui/index.html',
    '/static/css/2.b9b863b2.chunk.css': 'ui/static/css/2.b9b863b2.chunk.css',
    '/static/css/main.1359096b.chunk.css': 'ui/static/css/main.1359096b.chunk.css',
    '/static/js/2.e21fd42c.chunk.js': 'ui/static/js/2.e21fd42c.chunk.js',
    '/static/js/main.a57bb958.chunk.js': 'ui/static/js/main.a57bb958.chunk.js',
    '/static/js/runtime-main.ccc7405a.js': 'ui/static/js/runtime-main.ccc7405a.js'
}

class RequestHandler(BaseHTTPRequestHandler):
    device_database = None
    mqtt_client = None
    config_options = None
    agent_status_data = {}

    def send_json_response(self, data_dict):
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(bytes(json.dumps(data_dict), "utf-8"))

    def send_text_response(self, text_content, content_type="text/plain"):
        self.send_response(200)
        self.send_header("Content-type", content_type)
        self.end_headers()
        self.wfile.write(bytes(text_content, "utf-8"))

    def send_static_file(self, file_path, content_type):
        self.send_response(200)
        self.send_header("Content-type", content_type)
        self.end_headers()
        try:
            with open(file_path, 'rb') as f:
                self.wfile.write(f.read())
        except Exception as e:
            log(f"Error reading file {file_path}: {e}")

    def handle_root(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(bytes(
            '<!doctype html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/><title>Интеграция с умным домом Сбер</title></head><body>',
            "utf-8"))
        self.wfile.write(bytes('<h1>Управление устройствами</h1> <p><a href="index.html">Сбер Агент</a></p>', "utf-8"))
        self.wfile.write(bytes('<h1>Список устройств:</h1> <br>', "utf-8"))
        for entity_id in self.device_database.DB:
            device_name = self.device_database.DB[entity_id]['name']
            self.wfile.write(bytes(f"{entity_id}:{device_name}<br>", "utf-8"))
        self.wfile.write(bytes('</body></html>', "utf-8"))

    def handle_api_models(self):
        # TODO: Move this hardcoded list to a configuration file
        models_data = {
            "models": [
                {"id": "root_device", "manufacturer": "MQTT", "model": "MQTT Root Device", "description": "Root device model", "features": ["online"], "category": "hub"},
                {"id": "ID_1", "manufacturer": "Я", "model": "Моя модель", "hw_version": "1", "sw_version": "1", "description": "Моя модель", "features": ["online", "on_off"], "category": "relay"},
                {"id": "temp_device", "manufacturer": "tempDev", "model": "Термометр", "hw_version": "1", "sw_version": "1", "description": "Датчик температуры", "features": ["on_off", "online"], "category": "relay"},
                {"id": "ID_2", "manufacturer": "Я", "model": "Датчик температуры", "hw_version": "v1", "sw_version": "v1", "description": "Датчик температуры", "features": ["online", "temperature"], "category": "sensor_temp", "allowed_values": {"temperature": {"type": "INTEGER", "integer_values": {"min": "-400", "max": "2000"}}}}
            ]
        }
        self.send_json_response(models_data)

    def handle_api_devices_get(self):
        self.send_text_response(self.device_database.do_http_json_devices_list(), "application/json")

    def handle_api_devices_post(self, post_data):
        log(f"SberAgent adding new device: {post_data}")
        category = post_data.get('category', '')
        if category:
            new_id = self.device_database.new_id(category)
            self.device_database.DB[new_id] = {}
            self.device_database.update(new_id, post_data)
            self.device_database.save_db()
            self.mqtt_client.publish_config()

    def handle_api_v2_devices_post(self, post_data):
        log(f"Updating devices data: {post_data['devices']}")
        for device_entry in post_data['devices']:
            for entity_id, properties in device_entry.items():
                log(f"Updating {entity_id}: {properties}")
                self.device_database.update(entity_id, properties)
        self.mqtt_client.publish_config()
        self.device_database.save_db()

    def handle_api_v2_command_post(self, post_data):
        command = post_data.get('command', 'unknown')
        if command == 'DB_delete':
            log("Database deletion requested")
            self.device_database.clear(post_data)
        elif command == 'exit':
            log("Server shutdown requested")
            sys.exit()
        else:
            log(f"Received unknown command: {post_data}")

    def handle_api_v2_devices_get(self):
        self.send_text_response(self.device_database.do_http_json_devices_list_2(), "application/json")

    def handle_api_status(self):
        self.send_json_response(self.agent_status_data)

    def handle_api_categories(self):
        log('Requesting categories')
        self.send_json_response(sber_api.resCategories)

    def handle_api_proxy_v1(self):
        # Proxy request to Sber HTTP API
        api_prefix = '/api/v1/'
        log(f"PROXY {api_prefix}: {self.path}")
        
        target_url = f"{self.config_options['sber-http_api_endpoint']}/v1/mqtt-gate/{self.path[len(api_prefix):]}"
        headers = {'content-type': 'application/json'}
        auth = (self.config_options['sber-mqtt_login'], self.config_options['sber-mqtt_password'])
        
        try:
            response = requests.get(target_url, headers=headers, auth=auth)
            if response.status_code == 200:
                self.send_text_response(response.text, "application/json")
            else:
                log(f"PROXY ERROR! Request {target_url} failed with status: {response.status_code}")
        except Exception as e:
            log(f"PROXY Exception: {e}")

    def do_DELETE(self):
        self.send_json_response({})
        api_prefix = '/api/v1/devices/'
        if self.path.startswith(api_prefix):
            entity_id = self.path[len(api_prefix):]
            log(f"DELETE device: {entity_id}")
            self.device_database.dev_del(entity_id)
            self.mqtt_client.publish_config()

    def do_GET(self):
        static_file_path = STATIC_ROUTES.get(self.path)
        if static_file_path:
            _, ext = os.path.splitext(static_file_path)
            mime_type = MIME_TYPES.get(ext, MIME_TYPES['default'])
            
            # Строим полный путь относительно директории приложения
            full_path = os.path.join(APP_DIR, static_file_path)
            log(f"Serving file: {full_path} (MIME: {mime_type})")
            self.send_static_file(full_path, f"{mime_type}; charset=utf-8")
            return

        # API Routing
        routes = {
            '/': self.handle_root,
            '/api/v1/status': self.handle_api_status,
            '/api/v1/models': self.handle_api_models,
            '/api/v1/categories': self.handle_api_categories,
            '/api/v1/devices': self.handle_api_devices_get,
            '/api/v2/devices': self.handle_api_v2_devices_get
        }
        
        handler = routes.get(self.path)
        if handler:
            handler()
        elif self.path.startswith('/api/v1/'):
            self.handle_api_proxy_v1()
        else:
            self.send_text_response(f"Request: {self.path}", "text/html")

    def do_PUT(self):
        self.send_json_response({})
        log(f"PUT: {self.path}")
        content_length = int(self.headers['Content-Length'])
        put_data = json.loads(self.rfile.read(content_length))
        
        api_prefix = '/api/v1/devices/'
        if self.path.startswith(api_prefix):
            entity_id = self.path[len(api_prefix):]
            if entity_id == put_data.get('id'):
                self.device_database.update(entity_id, put_data)
                self.mqtt_client.publish_config()

    def do_POST(self):
        self.send_json_response({})
        log(f"POST: {self.path}")
        content_length = int(self.headers['Content-Length'])
        post_data = json.loads(self.rfile.read(content_length))
        
        routes = {
            '/api/v1/devices': self.handle_api_devices_post,
            '/api/v2/devices': self.handle_api_v2_devices_post,
            '/api/v2/command': self.handle_api_v2_command_post
        }
        
        handler = routes.get(self.path)
        if handler:
            handler(post_data)
        else:
            log(f"Unknown POST request: {post_data}")

class WebServer:
    def __init__(self, device_db, mqtt_client, config_options, agent_status):
        self.device_db = device_db
        self.mqtt_client = mqtt_client
        self.config_options = config_options
        self.agent_status = agent_status
        self.host_name = ''
        self.server_port = 9123
        self.server = None
        self.server_thread = None

    def start(self):
        RequestHandler.device_database = self.device_db
        RequestHandler.mqtt_client = self.mqtt_client
        RequestHandler.config_options = self.config_options
        RequestHandler.agent_status_data = self.agent_status
        
        self.server = HTTPServer((self.host_name, self.server_port), RequestHandler)
        log(f"Web server started at http://{self.host_name or 'localhost'}:{self.server_port}")
        
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            log("Web server stopped.")
