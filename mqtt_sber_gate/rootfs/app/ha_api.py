import json
import time
import requests
import websocket
from logger import log

class HAClient:
    def __init__(self, devices_db, options, publish_status_callback):
        self.device_database = devices_db
        self.config_options = options
        self.publish_status_callback = publish_status_callback
        self.areas_registry = {}
        self.devices_registry = {}
        self.websocket_client = None

    def get_api_headers(self):
        token = self.config_options.get('ha-api_token', '')
        return {
            'Authorization': f"Bearer {token}",
            'content-type': 'application/json'
        }

    def toggle_device_state(self, entity_id):
        is_on = self.device_database.get_state(entity_id, 'on_off')
        entity_domain, _ = entity_id.split('.', 1)
        log(f"Отправляем команду в HA для {entity_id} ON: {is_on}")
        
        api_url = self.config_options.get('ha-api_url', 'http://supervisor/core')
        base_url = f"{api_url}/api/services/{entity_domain}/"
        if entity_domain == 'button':
            url = base_url + 'press'
        else:
            url = base_url + ('turn_on' if is_on else 'turn_off')
            
        log(f"HA REST API REQUEST: {url}")
        requests.post(url, json={"entity_id": entity_id}, headers=self.get_api_headers())

    def set_climate_temperature(self, entity_id, changes):
        entity_domain, _ = entity_id.split('.', 1)
        log(f"Отправляем команду в HA для {entity_id} Climate: ")
        api_url = self.config_options.get('ha-api_url', 'http://supervisor/core')
        url = f"{api_url}/api/services/{entity_domain}/set_temperature"
        log(f"HA REST API REQUEST: {url}")
        
        target_temp = self.device_database.get_state(entity_id, 'hvac_temp_set')
        is_on = self.device_database.get_state(entity_id, 'on_off')
        
        payload = {
            "entity_id": entity_id,
            "temperature": target_temp,
            "hvac_mode": "cool" if is_on else "off"
        }
        requests.post(url, json=payload, headers=self.get_api_headers())

    def toggle_switch_state(self, entity_id, should_turn_on):
        log(f"Отправляем команду в HA для {entity_id} ON: {should_turn_on}")
        service = 'turn_on' if should_turn_on else 'turn_off'
        api_url = self.config_options.get('ha-api_url', 'http://supervisor/core')
        url = f"{api_url}/api/services/switch/{service}"
        requests.post(url, json={"entity_id": entity_id}, headers=self.get_api_headers())

    def execute_script(self, entity_id, should_turn_on):
        log(f"Отправляем команду в HA для {entity_id} ON: {should_turn_on}")
        service = 'turn_on' if should_turn_on else 'turn_off'
        api_url = self.config_options.get('ha-api_url', 'http://supervisor/core')
        url = f"{api_url}/api/services/script/{service}"
        requests.post(url, json={"entity_id": entity_id}, headers=self.get_api_headers())

    # Entity update helpers
    def update_switch_entity(self, entity_id, state_data):
        friendly_name = state_data['attributes'].get('friendly_name', '')
        log(f"switch: {entity_id} {friendly_name}", 0)
        self.device_database.update(entity_id, {
            'entity_ha': True,
            'entity_type': 'sw',
            'friendly_name': friendly_name,
            'category': 'relay'
        })

    def update_light_entity(self, entity_id, state_data):
        friendly_name = state_data['attributes'].get('friendly_name', '')
        log(f"light: {entity_id} {friendly_name}", 0)
        self.device_database.update(entity_id, {
            'entity_ha': True,
            'entity_type': 'light',
            'friendly_name': friendly_name,
            'category': 'light'
        })

    def update_script_entity(self, entity_id, state_data):
        friendly_name = state_data['attributes'].get('friendly_name', '')
        log(f"script: {entity_id} {friendly_name}", 0)
        self.device_database.update(entity_id, {
            'entity_ha': True,
            'entity_type': 'scr',
            'friendly_name': friendly_name,
            'category': 'relay'
        })

    def update_sensor_entity(self, entity_id, state_data):
        device_class = state_data['attributes'].get('device_class', '')
        friendly_name = state_data['attributes'].get('friendly_name', '')
        if device_class == 'temperature':
            self.device_database.update(entity_id, {
                'entity_ha': True,
                'entity_type': 'sensor_temp',
                'friendly_name': friendly_name,
                'category': 'sensor_temp'
            })

    def update_button_entity(self, entity_id, state_data):
        device_class = state_data['attributes'].get('device_class', '')
        friendly_name = state_data['attributes'].get('friendly_name', '')
        log(f"button: {entity_id} {friendly_name}({device_class})", 0)
        self.device_database.update(entity_id, {
            'entity_ha': True,
            'entity_type': 'button',
            'friendly_name': friendly_name,
            'category': 'relay'
        })

    def update_input_boolean_entity(self, entity_id, state_data):
        device_class = state_data['attributes'].get('device_class', '')
        friendly_name = state_data['attributes'].get('friendly_name', '')
        log(f"input_boolean: {entity_id} {friendly_name}({device_class})", 0)
        self.device_database.update(entity_id, {
            'entity_ha': True,
            'entity_type': 'input_boolean',
            'friendly_name': friendly_name,
            'category': 'scenario_button'
        })

    def update_climate_entity(self, entity_id, state_data):
        device_class = state_data['attributes'].get('device_class', '')
        friendly_name = state_data['attributes'].get('friendly_name', '')
        log(f"climate: {entity_id} {friendly_name}({device_class})", 0)
        self.device_database.update(entity_id, {
            'entity_ha': True,
            'entity_type': 'climate',
            'friendly_name': friendly_name,
            'category': 'hvac_ac'
        })

    def update_hvac_radiator_entity(self, entity_id, state_data):
        device_class = state_data['attributes'].get('device_class', '')
        friendly_name = state_data['attributes'].get('friendly_name', '')
        if device_class == 'temperature':
            self.device_database.update(entity_id, {
                'entity_ha': True,
                'entity_type': 'hvac_radiator',
                'friendly_name': friendly_name,
                'category': 'hvac_radiator'
            })

    def update_default_entity(self, entity_id, state_data):
        log(f"Неиспользуемый тип: {entity_id}", 0)
        pass

    def initialize_entities_via_rest(self):
        api_url = self.config_options.get('ha-api_url', 'http://supervisor/core')
        url = f"{api_url}/api/states"
        log(f"Подключаемся к HA, (ha-api_url: {api_url})", 3)
        
        attempt = 0
        response = None
        while attempt < 10:
            attempt += 1
            try:
                response = requests.get(url, headers=self.get_api_headers())
                break
            except Exception:
                log(f"Ошибка подключения к HA. Ждём 5 сек перед повторным подключением. Попытка {attempt}", 6)
                time.sleep(5)
        
        if response and response.status_code == 200:
            log('Запрос устройств из Home Assistant выполнен штатно. Обрабатываем полученный список')
            ha_entities = response.json()
            log(ha_entities, 0)
        else:
            log('ОШИБКА! Запрос устройств из Home Assistant выполнен некорректно.', 6)
            if response:
                log(f"Код ответа сервера: {response.status_code}", 6)
            ha_entities = []

        update_handlers = {
            'switch': self.update_switch_entity,
            'light': self.update_light_entity,
            'script': self.update_script_entity,
            'sensor': self.update_sensor_entity,
            'button': self.update_button_entity,
            'input_boolean': self.update_input_boolean_entity,
            'climate': self.update_climate_entity,
            'hvac_radiator': self.update_hvac_radiator_entity
        }

        for entity in ha_entities:
            entity_id = entity['entity_id']
            entity_type, _ = entity_id.split('.', 1)
            handler = update_handlers.get(entity_type, self.update_default_entity)
            handler(entity_id, entity)

    # WebSocket methods
    def on_websocket_open(self, ws):
        log("WebSocket: opened", 3)

    def on_websocket_close(self, ws, close_status_code, close_msg):
        log("WebSocket: Connection closed", 3)

    def on_websocket_message(self, ws, message):
        log(f"WebSocket: Received message: {message}", 0)
        message_data = json.loads(message)
        
        message_handlers = {
            'auth_required': self.handle_auth_required,
            'auth_ok': self.handle_auth_ok,
            'auth_invalid': self.handle_auth_invalid,
            'result': self.handle_websocket_result,
            'event': self.handle_websocket_event
        }
        
        handler = message_handlers.get(message_data.get('type'), self.handle_websocket_default)
        handler(ws, message_data)

    def handle_auth_required(self, ws, message_data):
        log("WebSocket: auth_required")
        token = self.config_options.get('ha-api_token', '')
        ws.send(json.dumps({
            "type": "auth",
            "access_token": token
        }))

    def handle_auth_ok(self, ws, message_data):
        log("WebSocket: auth_ok")
        ws.send(json.dumps({'id': 1, 'type': 'subscribe_events', 'event_type': 'state_changed'}))
        ws.send(json.dumps({'id': 2, 'type': 'config/area_registry/list'}))
        ws.send(json.dumps({'id': 3, 'type': 'config/device_registry/list'}))
        ws.send(json.dumps({'id': 4, 'type': 'config/entity_registry/list'}))

    def handle_auth_invalid(self, ws, message_data):
        log("WebSocket: auth_invalid, проверьте долгосрочный токен указанный в настройках плагина (ha-api_token)", 7)

    def handle_websocket_result(self, ws, message_data):
        log(f"WebSocket: result: {message_data}", 0)
        request_id = message_data.get('id')

        if request_id == 2:
            log(f"WebSocket: Получен список зон: {message_data}", 0)
            self.areas_registry = {}
            for area in message_data.get('result', []):
                self.areas_registry[area['area_id']] = area['name']
            log(f"HA_AREA: {self.areas_registry}", 1)

        elif request_id == 3:
            log(f"WebSocket: Получен список устройств (device_registry): {message_data}", 0)
            self.devices_registry = {}
            for device in message_data.get('result', []):
                device_id = device['id']
                self.devices_registry[device_id] = {
                    'id': device_id,
                    'name': device.get('name') or device.get('name_by_user') or 'Unknown',
                    'area_id': device.get('area_id', 'Unknown')
                }
            log(f"Обновлён HA_DEVICES: найдено {len(self.devices_registry)} устройств", 1)

        elif request_id == 4:
            log("WebSocket: Получен список сущностей.", 0)
            for entity in message_data.get('result', []):
                entity_id = entity['entity_id']
                db_entity = self.device_database.DB.get(entity_id)
                if not db_entity:
                    continue

                device_id = entity.get('device_id')
                area_id = None
                if device_id and device_id in self.devices_registry:
                    area_id = self.devices_registry[device_id].get('area_id')
                else:
                    area_id = entity.get('area_id')

                room_name = self.areas_registry.get(area_id, '') if area_id else ''
                current_room_in_db = db_entity.get('room')

                if current_room_in_db != room_name:
                    log(f"Изменилось расположение сущности {entity_id} с {current_room_in_db} на {room_name}")
                    self.device_database.update_only(entity_id, {
                        'entity_ha': True,
                        'room': room_name
                    })

    def handle_websocket_event(self, ws, message_data):
        event_data = message_data['event']['data']
        entity_id = event_data['new_state']['entity_id']
        old_state = event_data['old_state']['state'] if event_data.get('old_state') else 'None'
        new_state = event_data['new_state']['state']
        
        device_entry = self.device_database.DB.get(entity_id)
        
        # Debug logging for a specific sensor if needed
        if 'sensor.temperatura_kabinet' in entity_id:
            log(f"ANY Event: {entity_id}: {old_state} -> {new_state}")
            
        if device_entry and device_entry.get('enabled'):
            log(f"HA Event: {entity_id}: {old_state} -> {new_state}", 3)
            
            if device_entry['category'] == 'sensor_temp':
                try:
                    self.device_database.change_state(entity_id, 'temperature', float(new_state))
                except (ValueError, TypeError):
                    pass
            
            if new_state == 'on':
                self.device_database.change_state(entity_id, 'on_off', True)
                if 'button_event' in device_entry['States']:
                    device_entry['States']['button_event'] = 'click'
            else:
                if device_entry['entity_type'] == 'climate':
                    is_active = new_state != 'off'
                    self.device_database.change_state(entity_id, 'on_off', is_active)
                else:
                    self.device_database.change_state(entity_id, 'on_off', False)
                
                if 'button_event' in device_entry['States']:
                    device_entry['States']['button_event'] = 'double_click'
            
            # Send status update to Sber
            if self.publish_status_callback:
                status_payload = self.device_database.do_mqtt_json_states_list([entity_id])
                self.publish_status_callback(status_payload)

    def handle_websocket_default(self, ws, message_data):
        log("WebSocket: default")

    def run_websocket_client(self):
        api_url = self.config_options.get('ha-api_url', 'http://supervisor/core')
        ws_url = api_url.replace('http', 'ws', 1) + '/api/websocket'
        log(f"Start WebSocket Client URL: {ws_url}")
        
        self.websocket_client = websocket.WebSocketApp(
            ws_url,
            on_open=self.on_websocket_open,
            on_message=self.on_websocket_message,
            on_close=self.on_websocket_close
        )
        
        should_run = True
        while should_run:
            self.websocket_client.run_forever()
            log('Socket disconnect')
            time.sleep(1)
            log('Connecting')
