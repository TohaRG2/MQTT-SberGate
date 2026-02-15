import json
import time
import requests
import websocket
from logger import log

class HAClient:
    """
    Клиент для взаимодействия с Home Assistant через REST API и WebSocket.
    Обеспечивает синхронизацию состояний устройств и управление ими.
    """
    def __init__(self, devices_db, options, publish_status_callback):
        """Инициализация клиента HA."""
        self.device_database = devices_db
        self.config_options = options
        self.publish_status_callback = publish_status_callback
        self.areas_registry = {}
        self.devices_registry = {}
        self.websocket_client = None

    def get_api_headers(self):
        """Формирование заголовков для REST API запросов."""
        token = self.config_options.get('ha-api_token', '')
        return {
            'Authorization': f"Bearer {token}",
            'content-type': 'application/json'
        }

    def toggle_device_state(self, entity_id):
        """Переключение состояния устройства (вкл/выкл) в Home Assistant."""
        is_on = self.device_database.get_state(entity_id, 'on_off')
        entity_domain, _ = entity_id.split('.', 1)
        log(f"Отправляем команду в HA для {entity_id} ON: {is_on}")
        
        api_url = self.config_options.get('ha-api_url', 'http://supervisor/core')
        base_url = f"{api_url}/api/services/{entity_domain}/"
        
        payload = {"entity_id": entity_id}
        
        if entity_domain == 'button':
            url = base_url + 'press'
        else:
            service = 'turn_on' if is_on else 'turn_off'
            url = base_url + service
            
            # Если это лампа и она включается, проверяем наличие параметров в БД
            if entity_domain == 'light' and is_on:
                # Яркость
                brightness_sber = self.device_database.get_state(entity_id, 'light_brightness')
                if brightness_sber is not None:
                    # Конвертируем из диапазона Сбера (50-1000) обратно в HA (0-255)
                    ha_brightness = round(((float(brightness_sber) - 50) / 950.0) * 255)
                    ha_brightness = max(0, min(255, ha_brightness))
                    payload['brightness'] = ha_brightness
                    log(f"Добавляем яркость в команду HA для {entity_id}: Сбер:{brightness_sber} -> HA:{ha_brightness}")
                
                # RGB цвет
                light_colour = self.device_database.get_state(entity_id, 'light_colour')
                if light_colour and isinstance(light_colour, dict):
                    payload['rgb_color'] = [
                        light_colour.get('red', 255),
                        light_colour.get('green', 255),
                        light_colour.get('blue', 255)
                    ]
                    log(f"Добавляем RGB цвет в команду HA для {entity_id}: {payload['rgb_color']}")
                
                # Цветовая температура (только если нет RGB)
                if 'rgb_color' not in payload:
                    colour_temp_sber = self.device_database.get_state(entity_id, 'light_colour_temp')
                    if colour_temp_sber is not None:
                        # Конвертация Сбер (0-1000) обратно в mired (153-500)
                        ha_mireds = round((float(colour_temp_sber) / 1000.0) * (500 - 153) + 153)
                        ha_mireds = max(153, min(500, ha_mireds))
                        payload['color_temp'] = ha_mireds
                        log(f"Добавляем цветовую температуру в команду HA для {entity_id}: Сбер:{colour_temp_sber} -> HA:{ha_mireds} мired")
            
        log(f"HA REST API ЗАПРОС: {url} Данные: {payload}")
        requests.post(url, json=payload, headers=self.get_api_headers())

    def set_climate_temperature(self, entity_id, changes):
        """Установка целевой температуры для климатических устройств в Home Assistant."""
        entity_domain, _ = entity_id.split('.', 1)
        log(f"Отправляем команду в HA для {entity_id} Climate: ")
        api_url = self.config_options.get('ha-api_url', 'http://supervisor/core')
        url = f"{api_url}/api/services/{entity_domain}/set_temperature"
        log(f"HA REST API ЗАПРОС: {url}")
        
        target_temp = self.device_database.get_state(entity_id, 'hvac_temp_set')
        is_on = self.device_database.get_state(entity_id, 'on_off')
        
        payload = {
            "entity_id": entity_id,
            "temperature": target_temp,
            "hvac_mode": "cool" if is_on else "off"
        }
        requests.post(url, json=payload, headers=self.get_api_headers())

    def toggle_switch_state(self, entity_id, should_turn_on):
        """Управление переключателем в Home Assistant."""
        log(f"Отправляем команду в HA для {entity_id} ON: {should_turn_on}")
        service = 'turn_on' if should_turn_on else 'turn_off'
        api_url = self.config_options.get('ha-api_url', 'http://supervisor/core')
        url = f"{api_url}/api/services/switch/{service}"
        requests.post(url, json={"entity_id": entity_id}, headers=self.get_api_headers())

    def execute_script(self, entity_id, should_turn_on):
        """Запуск/остановка скрипта в Home Assistant."""
        log(f"Отправляем команду в HA для {entity_id} ON: {should_turn_on}")
        service = 'turn_on' if should_turn_on else 'turn_off'
        api_url = self.config_options.get('ha-api_url', 'http://supervisor/core')
        url = f"{api_url}/api/services/script/{service}"
        requests.post(url, json={"entity_id": entity_id}, headers=self.get_api_headers())

    # Помощники для обновления сущностей
    def update_switch_entity(self, entity_id, state_data):
        """Обновление сущности типа 'переключатель' (switch)."""
        friendly_name = state_data['attributes'].get('friendly_name', '')
        log(f"переключатель (switch): {entity_id} {friendly_name}", 0)
        self.device_database.update(entity_id, {
            'entity_ha': True,
            'entity_type': 'sw',
            'friendly_name': friendly_name,
            'category': 'relay'
        })
        is_on = state_data.get('state') == 'on'
        self.device_database.change_state(entity_id, 'on_off', is_on)

    def update_light_entity(self, entity_id, state_data):
        """Обновление сущности типа 'свет' (light)."""
        friendly_name = state_data['attributes'].get('friendly_name', '')
        log(f"свет (light): {entity_id} {friendly_name}", 0)
        self.device_database.update(entity_id, {
            'entity_ha': True,
            'entity_type': 'light',
            'friendly_name': friendly_name,
            'category': 'light'
        })
        is_on = state_data.get('state') == 'on'
        self.device_database.change_state(entity_id, 'on_off', is_on)
        
        # Обработка яркости
        brightness = state_data['attributes'].get('brightness')
        if brightness is not None:
            # Конвертируем из HA (0-255) в диапазон Сбера (50-1000)
            # Формула: sber = 50 + (ha * 950 / 255)
            sber_brightness = round(50 + (float(brightness) / 255.0) * 950)
            self.device_database.change_state(entity_id, 'light_brightness', sber_brightness)
        
        # Обработка RGB цвета
        supported_color_modes = state_data['attributes'].get('supported_color_modes', [])
        if 'rgb' in supported_color_modes or 'rgbw' in supported_color_modes or 'rgbww' in supported_color_modes:
            rgb_color = state_data['attributes'].get('rgb_color')
            if rgb_color and len(rgb_color) >= 3:
                # RGB в формате Сбера
                self.device_database.change_state(entity_id, 'light_colour', {
                    'red': rgb_color[0],
                    'green': rgb_color[1],
                    'blue': rgb_color[2]
                })
                self.device_database.change_state(entity_id, 'light_mode', 'colour')
        
        # Обработка цветовой температуры
        if 'color_temp' in supported_color_modes:
            color_temp = state_data['attributes'].get('color_temp')
            if color_temp is not None:
                # Конвертация mired (153-500) в Сбер (0-1000)
                # 153 mired (холодный ~6500K) -> 0
                # 500 mired (теплый ~2000K) -> 1000
                sber_temp = round(((color_temp - 153) / (500 - 153)) * 1000)
                sber_temp = max(0, min(1000, sber_temp))
                self.device_database.change_state(entity_id, 'light_colour_temp', sber_temp)
                # Если нет RGB, то режим белый
                if not self.device_database.get_state(entity_id, 'light_colour'):
                    self.device_database.change_state(entity_id, 'light_mode', 'white')

    def update_script_entity(self, entity_id, state_data):
        """Обновление сущности типа 'скрипт' (script)."""
        friendly_name = state_data['attributes'].get('friendly_name', '')
        log(f"скрипт (script): {entity_id} {friendly_name}", 0)
        self.device_database.update(entity_id, {
            'entity_ha': True,
            'entity_type': 'scr',
            'friendly_name': friendly_name,
            'category': 'relay'
        })
        is_on = state_data.get('state') == 'on'
        self.device_database.change_state(entity_id, 'on_off', is_on)

    def update_sensor_entity(self, entity_id, state_data):
        """Обновление сущности типа 'датчик' (sensor)."""
        device_class = state_data['attributes'].get('device_class', '')
        friendly_name = state_data['attributes'].get('friendly_name', '')
        if device_class == 'temperature':
            self.device_database.update(entity_id, {
                'entity_ha': True,
                'entity_type': 'sensor_temp',
                'friendly_name': friendly_name,
                'category': 'sensor_temp',
                'device_class': device_class
            })
        elif device_class == 'humidity':
            self.device_database.update(entity_id, {
                'entity_ha': True,
                'entity_type': 'sensor_temp',
                'friendly_name': friendly_name,
                'category': 'sensor_temp',
                'device_class': device_class
            })
        elif device_class == 'pressure':
            self.device_database.update(entity_id, {
                'entity_ha': True,
                'entity_type': 'sensor_temp',
                'friendly_name': friendly_name,
                'category': 'sensor_temp',
                'device_class': device_class
            })

    def update_button_entity(self, entity_id, state_data):
        """Обновление сущности типа 'кнопка' (button)."""
        device_class = state_data['attributes'].get('device_class', '')
        friendly_name = state_data['attributes'].get('friendly_name', '')
        log(f"кнопка (button): {entity_id} {friendly_name}({device_class})", 0)
        self.device_database.update(entity_id, {
            'entity_ha': True,
            'entity_type': 'button',
            'friendly_name': friendly_name,
            'category': 'relay'
        })

    def update_input_boolean_entity(self, entity_id, state_data):
        """Обновление сущности типа 'переключатель' (input_boolean)."""
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
        """Обновление сущности типа 'климат' (climate)."""
        device_class = state_data['attributes'].get('device_class', '')
        friendly_name = state_data['attributes'].get('friendly_name', '')
        log(f"климат (climate): {entity_id} {friendly_name}({device_class})", 0)
        self.device_database.update(entity_id, {
            'entity_ha': True,
            'entity_type': 'climate',
            'friendly_name': friendly_name,
            'category': 'hvac_ac'
        })

    def update_hvac_radiator_entity(self, entity_id, state_data):
        """Обновление сущности типа 'радиатор' (hvac_radiator)."""
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
        """Обработчик по умолчанию для неиспользуемых типов сущностей."""
        log(f"Неиспользуемый тип: {entity_id}", 0)
        pass

    def initialize_entities_via_rest(self):
        """Первоначальная загрузка всех сущностей из HA через REST API."""
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

        # Шаг 1: Инициализируем все сущности
        for entity in ha_entities:
            entity_id = entity['entity_id']
            entity_type, _ = entity_id.split('.', 1)
            handler = update_handlers.get(entity_type, self.update_default_entity)
            handler(entity_id, entity)
        
        # Шаг 2: Объединяем значения температуры, влажности и давления для датчиков с одним device_id
        sensor_temp_devices = {}
        for entity in ha_entities:
            entity_id = entity['entity_id']
            db_entity = self.device_database.devices_registry.get(entity_id)
            if db_entity and db_entity.get('category') == 'sensor_temp':
                device_class = entity['attributes'].get('device_class', '')
                if device_class in ['temperature', 'humidity', 'pressure']:
                    device_id = db_entity.get('device_id')
                    if device_id:
                        if device_id not in sensor_temp_devices:
                            sensor_temp_devices[device_id] = []
                        sensor_temp_devices[device_id].append(entity_id)
        
        # Теперь для каждого device_id объединяем значения
        for device_id, entity_ids in sensor_temp_devices.items():
            if len(entity_ids) > 1:
                # Собираем все доступные значения температуры, влажности и давления
                combined_states = {}
                for entity_id in entity_ids:
                    states = self.device_database.get_states(entity_id)
                    for key, value in states.items():
                        if key in ['temperature', 'humidity', 'air_pressure']:
                            combined_states[key] = value
                
                # Обновляем все датчики с этим device_id значениями из combined_states
                for entity_id in entity_ids:
                    for key, value in combined_states.items():
                        self.device_database.change_state(entity_id, key, value)

    # Методы WebSocket
    def on_websocket_open(self, ws):
        """Обработчик открытия WebSocket соединения."""
        log("WebSocket: соединение открыто", 3)

    def on_websocket_close(self, ws, close_status_code, close_msg):
        """Обработчик закрытия WebSocket соединения."""
        log("WebSocket: соединение закрыто", 3)

    def on_websocket_message(self, ws, message):
        """Обработчик входящих сообщений WebSocket."""
        log(f"WebSocket: получено сообщение: {message}", 0)
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
        """Обработка запроса авторизации WebSocket."""
        log("WebSocket: требуется авторизация")
        token = self.config_options.get('ha-api_token', '')
        ws.send(json.dumps({
            "type": "auth",
            "access_token": token
        }))

    def handle_auth_ok(self, ws, message_data):
        """Обработка успешной авторизации WebSocket."""
        log("WebSocket: авторизация успешна")
        ws.send(json.dumps({'id': 1, 'type': 'subscribe_events', 'event_type': 'state_changed'}))
        ws.send(json.dumps({'id': 2, 'type': 'config/area_registry/list'}))
        ws.send(json.dumps({'id': 3, 'type': 'config/device_registry/list'}))
        ws.send(json.dumps({'id': 4, 'type': 'config/entity_registry/list'}))

    def handle_auth_invalid(self, ws, message_data):
        """Обработка ошибки авторизации WebSocket."""
        log("WebSocket: ошибка авторизации, проверьте токен (ha-api_token)", 7)

    def handle_websocket_result(self, ws, message_data):
        """Обработка результатов выполнения запросов WebSocket."""
        log(f"WebSocket: результат: {message_data}", 0)
        request_id = message_data.get('id')

        if request_id == 2:
            log(f"WebSocket: Получен список зон (areas): {message_data}", 0)
            self.areas_registry = {}
            for area in message_data.get('result', []):
                self.areas_registry[area['area_id']] = area['name']
            log(f"ЗОНЫ HA: {self.areas_registry}", 1)

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
            log(f"ОБНОВЛЕНИЕ УСТРОЙСТВ HA: найдено {len(self.devices_registry)} устройств", 1)

        elif request_id == 4:
            log("WebSocket: Получен список сущностей (entities).", 0)
            for entity in message_data.get('result', []):
                entity_id = entity['entity_id']
                db_entity = self.device_database.devices_registry.get(entity_id)
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

                # Обновляем device_id устройства
                if device_id != db_entity.get('device_id'):
                    self.device_database.update(entity_id, {
                        'entity_ha': True,
                        'device_id': device_id
                    })

                if current_room_in_db != room_name:
                    log(f"Изменилось расположение сущности {entity_id} с '{current_room_in_db}' на '{room_name}'")
                    self.device_database.update(entity_id, {
                        'entity_ha': True,
                        'room': room_name
                    })

    def handle_websocket_event(self, ws, message_data):
        """Обработка событий изменения состояния WebSocket."""
        event_data = message_data['event']['data']
        if not event_data.get('new_state'):
            return
            
        entity_id = event_data['new_state']['entity_id']
        old_state = event_data['old_state']['state'] if event_data.get('old_state') else 'None'
        new_state = event_data['new_state']['state']
        
        device_entry = self.device_database.devices_registry.get(entity_id)
        
        if device_entry:
            device_class = event_data['new_state']['attributes'].get('device_class', '')
            current_device_id = device_entry.get('device_id')
            is_enabled = device_entry.get('enabled', False)
            
            # Обновление состояний датчиков
            if device_entry['category'] == 'sensor_temp':
                if device_class in ['temperature', 'humidity', 'pressure']:
                    try:
                        value = float(new_state)
                        key = ''
                        if device_class == 'temperature':
                            key = 'temperature'
                        elif device_class == 'humidity':
                            key = 'humidity'
                        elif device_class == 'pressure':
                            key = 'air_pressure'
                        
                        if key:
                            self.device_database.change_state(entity_id, key, value)
                            
                            # Синхронизация значений между датчиками одного устройства
                            if current_device_id:
                                for other_entity_id, other_device in self.device_database.devices_registry.items():
                                    if (other_device.get('device_id') == current_device_id and 
                                        other_device.get('category') == 'sensor_temp' and 
                                        other_entity_id != entity_id):
                                        self.device_database.change_state(other_entity_id, key, value)
                                        if other_device.get('enabled', False):
                                            self.publish_status_callback([other_entity_id])
                    except (ValueError, TypeError):
                        pass

            # Обновление состояний переключателей, света и скриптов
            elif device_entry['category'] in ['relay', 'light']:
                is_on = new_state == 'on'
                self.device_database.change_state(entity_id, 'on_off', is_on)
                
                # Обновление параметров для света
                if device_entry['category'] == 'light':
                    attributes = event_data['new_state']['attributes']
                    
                    # Яркость
                    brightness = attributes.get('brightness')
                    if brightness is not None:
                        sber_brightness = round(50 + (float(brightness) / 255.0) * 950)
                        self.device_database.change_state(entity_id, 'light_brightness', sber_brightness)
                    
                    # RGB цвет
                    rgb_color = attributes.get('rgb_color')
                    if rgb_color and len(rgb_color) >= 3:
                        self.device_database.change_state(entity_id, 'light_colour', {
                            'red': rgb_color[0],
                            'green': rgb_color[1],
                            'blue': rgb_color[2]
                        })
                        self.device_database.change_state(entity_id, 'light_mode', 'colour')
                    
                    # Цветовая температура
                    color_temp = attributes.get('color_temp')
                    if color_temp is not None:
                        sber_temp = round(((color_temp - 153) / (500 - 153)) * 1000)
                        sber_temp = max(0, min(1000, sber_temp))
                        self.device_database.change_state(entity_id, 'light_colour_temp', sber_temp)
                        # Если нет RGB, то режим белый
                        if not self.device_database.get_state(entity_id, 'light_colour'):
                            self.device_database.change_state(entity_id, 'light_mode', 'white')

            # Публикация в Сбер, если устройство активно
            if is_enabled:
                self.publish_status_callback([entity_id])

    def handle_websocket_default(self, ws, message_data):
        """Обработчик по умолчанию для неизвестных типов сообщений WebSocket."""
        pass

    def run_websocket_client(self):
        """Запуск WebSocket клиента в бесконечном цикле с автореконнектом."""
        websocket_url = self.config_options.get('ha-api_url', 'ws://supervisor/core/websocket')
        if websocket_url.startswith('http'):
            websocket_url = websocket_url.replace('http', 'ws', 1)
        if not websocket_url.endswith('/websocket'):
            websocket_url = websocket_url + '/api/websocket'

        while True:
            try:
                log(f"WebSocket: попытка подключения к {websocket_url}", 3)
                self.websocket_client = websocket.WebSocketApp(
                    websocket_url,
                    on_open=self.on_websocket_open,
                    on_message=self.on_websocket_message,
                    on_error=lambda ws, err: log(f"WebSocket: ошибка: {err}", 6),
                    on_close=self.on_websocket_close
                )
                self.websocket_client.run_forever()
            except Exception as e:
                log(f"WebSocket: критическая ошибка: {e}", 7)
            
            log("WebSocket: переподключение через 5 секунд...", 3)
            time.sleep(5)
