#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os
import sys
import time
from logger import log, set_log_level, check_log_file_size, LOG_FILE
from config import OPTIONS, DEVICES_DB_FILE_PATH, write_json_file, VERSION, update_option
from devices_db import CDevicesDB
from ha_api import HAClient
from mqtt_client import SberMQTTClient
from web_server import WebServer
import sber_api

# Инициализация логирования
current_log_level = OPTIONS.get('log_level', 'info')
set_log_level(current_log_level)

# Проверка размера лог-файла
check_log_file_size()

log(f"Starting MQTT SberGate IoT Agent for Home Assistant version: {VERSION}")
log(f"Operating System: {os.name}")
log(f"Python Version: {sys.version}")
log(f"Script Path: {os.path.realpath(__file__)}")
log(f"Current Directory: {os.getcwd()}")
log(f"Log File Size: {os.path.getsize(LOG_FILE)} bytes")
log(f"Log Level: {current_log_level}")
log(f"Default Encoding: {sys.getdefaultencoding()}")
log(f"Directory Files: {os.listdir('.')}")

# Проверка существования базы данных устройств
if not os.path.exists(DEVICES_DB_FILE_PATH):
    log(f"Database file not found, creating new one at {DEVICES_DB_FILE_PATH}")
    write_json_file(DEVICES_DB_FILE_PATH, {})

log('Loading device database from devices.json', 3)
device_db_manager = CDevicesDB(DEVICES_DB_FILE_PATH)

# Инициализация MQTT клиента Сбера
sber_mqtt_handler = SberMQTTClient(device_db_manager, OPTIONS)

# Инициализация клиента Home Assistant
ha_integration_client = HAClient(device_db_manager, OPTIONS, sber_mqtt_handler.send_status)

# Связывание MQTT клиента с клиентом HA
sber_mqtt_handler.set_ha_client(ha_integration_client)

# Загрузка начальных состояний из Home Assistant через REST API
ha_integration_client.initialize_entities_via_rest()

# Запуск MQTT клиента
sber_mqtt_handler.start()

# Ожидание получения endpoint-а SberDevice HTTP API
if OPTIONS.get('sber-http_api_endpoint', None) is None:
    update_option('sber-http_api_endpoint', '')

while not OPTIONS['sber-http_api_endpoint']:
    log('Waiting for SberDevice http_api_endpoint...')
    time.sleep(1)

log(f"SberDevice http_api_endpoint received: {OPTIONS['sber-http_api_endpoint']}")

# Загрузка моделей и инициализация категорий
sber_api.fetch_models()
sber_api.init_categories()

# Публикация конфигурации устройств в MQTT
sber_mqtt_handler.publish_config()

# Текущий статус агента
agent_status_report = {
    "online": True, 
    "error": "", 
    "credentials": {
        'username': OPTIONS['sber-mqtt_login'], 
        "password": "***",
        'broker': OPTIONS['sber-mqtt_broker']
    }
}

# Запуск веб-сервера для управления и мониторинга
api_web_server = WebServer(device_db_manager, sber_mqtt_handler, OPTIONS, agent_status_report)
api_web_server.start()

# Запуск WebSocket клиента Home Assistant (блокирующая операция)
try:
    log("Starting Home Assistant WebSocket listener...")
    ha_integration_client.run_websocket_client()
except KeyboardInterrupt:
    log("Agent received shutdown signal")
finally:
    log("Stopping API web server...")
    api_web_server.stop()

# Основной цикл (если WebSocket завершится)
while True:
    time.sleep(10)
    log('Agent Heartbeat')
