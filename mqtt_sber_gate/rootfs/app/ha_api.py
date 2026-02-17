import json
import time
import requests
import websocket
from logger import log_info, log_debug, log_trace, log_deeptrace, log_warning, log_error, log_fatal
from converters import (
    ha_brightness_to_sber,
    sber_brightness_to_ha,
    ha_temp_to_sber,
    sber_temp_to_ha
)

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
        log_info(f"Отправляем команду в HA для {entity_id} ON: {is_on}")
        
        api_url = self.config_options.get('ha-api_url', 'http://supervisor/core')
        base_url = f"{api_url}/api/services/{entity_domain}/"
        
        payload = {"entity_id": entity_id}
        
        if entity_domain == 'button' or entity_domain == 'input_button':
            url = base_url + 'press'
            log_deeptrace(f"Отправка события press для кнопки {entity_id}")
        else:
            service = 'turn_on' if is_on else 'turn_off'
            url = base_url + service
            
            # Если это лампа и она включается, проверяем наличие параметров в БД
            if entity_domain == 'light' and is_on:
                # Яркость
                brightness_sber = self.device_database.get_state(entity_id, 'light_brightness')
                if brightness_sber is not None:
                    ha_brightness = sber_brightness_to_ha(brightness_sber)
                    payload['brightness'] = ha_brightness
                    log_info(f"Добавляем яркость в команду HA для {entity_id}: Сбер:{brightness_sber} -> HA:{ha_brightness}")
                
                # RGB цвет
                light_colour = self.device_database.get_state(entity_id, 'light_colour')
                if light_colour and isinstance(light_colour, dict):
                    payload['rgb_color'] = [
                        light_colour.get('red', 255),
                        light_colour.get('green', 255),
                        light_colour.get('blue', 255)
                    ]
                    log_info(f"Добавляем RGB цвет в команду HA для {entity_id}: {payload['rgb_color']}")
                
                # Цветовая температура (только если нет RGB)
                if 'rgb_color' not in payload:
                    colour_temp_sber = self.device_database.get_state(entity_id, 'light_colour_temp')
                    if colour_temp_sber is not None:
                        ha_mireds = sber_temp_to_ha(colour_temp_sber)
                        payload['color_temp'] = ha_mireds
                        log_info(f"Добавляем цветовую температуру в команду HA для {entity_id}: Сбер:{colour_temp_sber} -> HA:{ha_mireds} мired")
            
        log_debug(f"Rest запрос в HA: {url} Данные: {payload}")
        requests.post(url, json=payload, headers=self.get_api_headers())

    def set_climate_temperature(self, entity_id, changes):
        """Установка целевой температуры для климатических устройств в Home Assistant."""
        entity_domain, _ = entity_id.split('.', 1)
        log_info(f"Отправляем команду в HA для {entity_id} Climate: ")
        api_url = self.config_options.get('ha-api_url', 'http://supervisor/core')
        url = f"{api_url}/api/services/{entity_domain}/set_temperature"
        log_debug(f"Rest запрос в HA: {url}")
        
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
        log_info(f"Отправляем команду в HA для {entity_id} ON: {should_turn_on}")
        service = 'turn_on' if should_turn_on else 'turn_off'
        api_url = self.config_options.get('ha-api_url', 'http://supervisor/core')
        url = f"{api_url}/api/services/switch/{service}"
        requests.post(url, json={"entity_id": entity_id}, headers=self.get_api_headers())

    def execute_script(self, entity_id, should_turn_on):
        """Запуск/остановка скрипта в Home Assistant."""
        log_info(f"Отправляем команду в HA для {entity_id} ON: {should_turn_on}")
        service = 'turn_on' if should_turn_on else 'turn_off'
        api_url = self.config_options.get('ha-api_url', 'http://supervisor/core')
        url = f"{api_url}/api/services/script/{service}"
        requests.post(url, json={"entity_id": entity_id}, headers=self.get_api_headers())

    # Помощники для обновления сущностей
    def update_switch_entity(self, entity_id, state_data):
        """Обновление сущности типа 'переключатель' (switch)."""
        friendly_name = state_data['attributes'].get('friendly_name', '')
        log_deeptrace(f"переключатель (switch): {entity_id} {friendly_name}")
        self.device_database.update(entity_id, {
            'entity_ha': True,
            'entity_type': 'switch',
            'friendly_name': friendly_name,
            'category': 'relay'
        })
        is_on = state_data.get('state') == 'on'
        self.device_database.change_state(entity_id, 'on_off', is_on)

    def update_light_entity(self, entity_id, state_data):
        """Обновление сущности типа 'свет' (light)."""
        friendly_name = state_data['attributes'].get('friendly_name', '')
        log_deeptrace(f"свет (light): {entity_id} {friendly_name}")
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
            sber_brightness = ha_brightness_to_sber(brightness)
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
                sber_temp = ha_temp_to_sber(color_temp)
                self.device_database.change_state(entity_id, 'light_colour_temp', sber_temp)
                # Если нет RGB, то режим белый
                if not self.device_database.get_state(entity_id, 'light_colour'):
                    self.device_database.change_state(entity_id, 'light_mode', 'white')

    def update_script_entity(self, entity_id, state_data):
        """Обновление сущности типа 'скрипт' (script)."""
        friendly_name = state_data['attributes'].get('friendly_name', '')
        log_deeptrace(f"скрипт (script): {entity_id} {friendly_name}")
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
        elif device_class == 'pressure' or device_class == 'atmospheric_pressure':
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
        log_deeptrace(f"кнопка (button): {entity_id} {friendly_name}({device_class})")
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
        log_deeptrace(f"input_boolean: {entity_id} {friendly_name}({device_class})")
        self.device_database.update(entity_id, {
            'entity_ha': True,
            'entity_type': 'input_boolean',
            'friendly_name': friendly_name,
            'category': 'scenario_button'
        })

    def update_input_button_entity(self, entity_id, state_data):
        """Обновление сущности типа 'кнопка' (input_button)."""
        device_class = state_data['attributes'].get('device_class', '')
        friendly_name = state_data['attributes'].get('friendly_name', '')
        log_deeptrace(f"input_button: {entity_id} {friendly_name}({device_class})")
        self.device_database.update(entity_id, {
            'entity_ha': True,
            'entity_type': 'input_button',
            'friendly_name': friendly_name,
            'category': 'scenario_button'
        })

    def update_climate_entity(self, entity_id, state_data):
        """Обновление сущности типа 'климат' (climate)."""
        device_class = state_data['attributes'].get('device_class', '')
        friendly_name = state_data['attributes'].get('friendly_name', '')
        log_deeptrace(f"климат (climate): {entity_id} {friendly_name}({device_class})")
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
        log_deeptrace(f"Неиспользуемый тип: {entity_id}")
        pass

    def initialize_entities_via_rest(self):
        """Первоначальная загрузка всех сущностей из HA через REST API."""
        api_url = self.config_options.get('ha-api_url', 'http://supervisor/core')
        url = f"{api_url}/api/states"
        log_info(f"Подключаемся к HA, (ha-api_url: {api_url})")
        
        attempt = 0
        response = None
        while attempt < 10:
            attempt += 1
            try:
                response = requests.get(url, headers=self.get_api_headers())
                break
            except Exception:
                log_error(f"Ошибка подключения к HA. Ждём 5 сек перед повторным подключением. Попытка {attempt}")
                time.sleep(5)
        
        if response and response.status_code == 200:
            log_info('Запрос устройств из Home Assistant выполнен штатно. Обрабатываем полученный список')
            ha_entities = response.json()
            log_deeptrace(ha_entities)
        else:
            log_error('ОШИБКА! Запрос устройств из Home Assistant выполнен некорректно.')
            if response:
                log_error(f"Код ответа сервера: {response.status_code}")
            ha_entities = []

        update_handlers = {
            'switch': self.update_switch_entity,
            'light': self.update_light_entity,
            'script': self.update_script_entity,
            'sensor': self.update_sensor_entity,
            'button': self.update_button_entity,
            'input_boolean': self.update_input_boolean_entity,
            'input_button': self.update_input_button_entity,
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
                if device_class in ['temperature', 'humidity', 'pressure', 'atmospheric_pressure']:
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
        log_info("WebSocket: соединение открыто")

    def on_websocket_close(self, ws, close_status_code, close_msg):
        """Обработчик закрытия WebSocket соединения."""
        log_info("WebSocket: соединение закрыто")

    def on_websocket_message(self, ws, message):
        """Обработчик входящих сообщений WebSocket."""
        log_deeptrace(f"WebSocket: получено сообщение: {message}")
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
        log_info("WebSocket: требуется авторизация")
        token = self.config_options.get('ha-api_token', '')
        try:
            ws.send(json.dumps({
                "type": "auth",
                "access_token": token
            }))
        except Exception as e:
            log_error(f"Ошибка отправки auth через WebSocket: {e}")

    def handle_auth_ok(self, ws, message_data):
        """Обработка успешной авторизации WebSocket."""
        log_info("WebSocket: авторизация успешна")
        try:
            ws.send(json.dumps({'id': 1, 'type': 'subscribe_events', 'event_type': 'state_changed'}))
            ws.send(json.dumps({'id': 2, 'type': 'config/area_registry/list'}))
            ws.send(json.dumps({'id': 3, 'type': 'config/device_registry/list'}))
            ws.send(json.dumps({'id': 4, 'type': 'config/entity_registry/list'}))
        except Exception as e:
            log_error(f"Ошибка отправки команд через WebSocket: {e}")

    def handle_auth_invalid(self, ws, message_data):
        """Обработка ошибки авторизации WebSocket."""
        log_fatal("WebSocket: ошибка авторизации, проверьте токен (ha-api_token)")

    def handle_websocket_result(self, ws, message_data):
        """Обработка результатов выполнения запросов WebSocket."""
        log_deeptrace(f"WebSocket: результат: {message_data}")
        request_id = message_data.get('id')

        if request_id == 2:
            log_deeptrace(f"WebSocket: Получен список зон (areas): {message_data}")
            self.areas_registry = {}
            for area in message_data.get('result', []):
                self.areas_registry[area['area_id']] = area['name']
            log_trace(f"ЗОНЫ HA: {self.areas_registry}")

        elif request_id == 3:
            log_deeptrace(f"WebSocket: Получен список устройств (device_registry): {message_data}")
            self.devices_registry = {}
            for device in message_data.get('result', []):
                device_id = device['id']
                self.devices_registry[device_id] = {
                    'id': device_id,
                    'name': device.get('name') or device.get('name_by_user') or 'Unknown',
                    'area_id': device.get('area_id', 'Unknown')
                }
            log_trace(f"ОБНОВЛЕНИЕ УСТРОЙСТВ HA: найдено {len(self.devices_registry)} устройств")

        elif request_id == 4:
            log_deeptrace("WebSocket: Получен список сущностей (entities).")
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
                    log_info(f"Изменилось расположение сущности {entity_id} с '{current_room_in_db}' на '{room_name}'")
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
        
        # Логирование нового состояния от HA
        is_active = device_entry and device_entry.get('enabled', False)
        if is_active:
            log_debug(f"!Получено новое состояние от HA для: {entity_id} {old_state} -> {new_state}")
        else:
            log_deeptrace(f"Получено новое состояние от HA для какого-то: {entity_id} {old_state} -> {new_state}")

        if device_entry:
            device_class = event_data['new_state']['attributes'].get('device_class', '')
            current_device_id = device_entry.get('device_id')
            is_enabled = device_entry.get('enabled', False)
            
            # Обновление состояний датчиков
            if device_entry['category'] == 'sensor_temp':
                if device_class in ['temperature', 'humidity', 'pressure', 'atmospheric_pressure']:
                    try:
                        value = float(new_state)
                        key = ''
                        if device_class == 'temperature':
                            key = 'temperature'
                        elif device_class == 'humidity':
                            key = 'humidity'
                        elif device_class == 'pressure' or device_class == 'atmospheric_pressure':
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
                                            payload = self.device_database.do_mqtt_json_states_list([other_entity_id])
                                            self.publish_status_callback(payload)
                    except (ValueError, TypeError):
                        pass

            # Обновление состояний кнопок (scenario_button)
            elif device_entry['category'] == 'scenario_button':
                if device_entry.get('entity_type') == 'input_boolean':
                    if new_state == 'on':
                        self.device_database.change_state(entity_id, 'button_event', 'click')
                    elif new_state == 'off':
                        self.device_database.change_state(entity_id, 'button_event', 'double_click')
                elif device_entry.get('entity_type') == 'input_button':
                    self.device_database.change_state(entity_id, 'button_event', 'click')

            # Обновление состояний переключателей, света и скриптов
            elif device_entry['category'] in ['relay', 'light']:
                # Логика фильтрации эха через ожидаемое состояние
                expected_state = device_entry.get('_expected_mqtt_state')
                
                if device_entry.get('entity_type') == 'button':
                    # Для кнопки просто игнорируем, если ожидаем реакцию
                    if expected_state is not None:
                        log_deeptrace(f"Игнорируем эхо кнопки {entity_id}")
                        device_entry.pop('_expected_mqtt_state', None)
                        return
                        
                    # Обработка кнопки как переключателя
                    attributes = event_data['new_state'].get('attributes', {})
                    click_type = attributes.get('click_type') or attributes.get('event_type')
                    
                    if click_type in ['double_click', 'long_press']:
                        self.device_database.change_state(entity_id, 'on_off', False)
                    else:
                        self.device_database.change_state(entity_id, 'on_off', True)
                
                else:
                    # Для переключателей/ламп
                    is_on = new_state == 'on'
                    
                    # Если есть ожидаемое состояние от MQTT
                    if expected_state is not None:
                        # Если пришло то, что ожидали (или противоположное из-за лага)
                        # Мы просто сбрасываем ожидание, но НЕ отправляем обновление в Сбер,
                        # так как Сбер и так знает это состояние (он его и прислал)
                        if is_on == expected_state:
                            log_deeptrace(f"Получено ожидаемое состояние {is_on} для {entity_id}. Эхо подавлено.")
                            device_entry.pop('_expected_mqtt_state', None)
                            return
                        else:
                            # Пришло промежуточное состояние (не то, что ждали)
                            # Игнорируем его, ждем правильного
                            log_deeptrace(f"Игнорируем промежуточное состояние {is_on} для {entity_id} (ждем {expected_state})")
                            return

                    # Штатная обработка изменений (ручное управление)
                    current_on_off = self.device_database.get_state(entity_id, 'on_off')
                    if is_on != current_on_off:
                        # Проверка на дребезг контактов (игнорируем мгновенные переключения)
                        last_change = device_entry.get('_last_state_change_ts', 0)
                        now = time.time()
                        
                        # Если состояние меняется слишком быстро (<0.5 сек) и это не ожидаемая команда
                        if now - last_change < 0.5:
                             log_deeptrace(f"Игнорируем слишком частое переключение {entity_id}")
                             return

                        device_entry['_last_state_change_ts'] = now
                        self.device_database.change_state(entity_id, 'on_off', is_on)
                    else:
                         log_deeptrace(f"Состояние {entity_id} не изменилось ({is_on}), пропускаем обновление Сбера")
                         return
                
                # Обновление параметров для света
                if device_entry['category'] == 'light':
                    attributes = event_data['new_state']['attributes']
                    
                    # Яркость
                    brightness = attributes.get('brightness')
                    if brightness is not None:
                        sber_brightness = ha_brightness_to_sber(brightness)
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
                        sber_temp = ha_temp_to_sber(color_temp)
                        self.device_database.change_state(entity_id, 'light_colour_temp', sber_temp)
                        # Если нет RGB, то режим белый
                        if not self.device_database.get_state(entity_id, 'light_colour'):
                            self.device_database.change_state(entity_id, 'light_mode', 'white')

            # Публикация в Сбер, если устройство активно
            if is_enabled:
                payload = self.device_database.do_mqtt_json_states_list([entity_id])
                self.publish_status_callback(payload)

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
                log_info(f"WebSocket: попытка подключения к {websocket_url}")
                self.websocket_client = websocket.WebSocketApp(
                    websocket_url,
                    on_open=self.on_websocket_open,
                    on_message=self.on_websocket_message,
                    on_error=lambda ws, err: log_error(f"WebSocket: ошибка: {err}"),
                    on_close=self.on_websocket_close
                )
                # Запускаем с ping_interval для поддержания соединения
                # ping_interval - как часто отправлять ping (30 сек)
                # ping_timeout - сколько ждать pong ответа (2 сек, должно быть меньше interval)
                # ping_payload - данные для ping (должны быть строкой или байтами)
                self.websocket_client.run_forever(
                    ping_interval=30,
                    ping_timeout=3,
                    ping_payload=b'ping'
                )
            except Exception as e:
                log_fatal(f"WebSocket: критическая ошибка: {e}")
            
            log_info("WebSocket: переподключение через 5 секунд...")
            time.sleep(5)
