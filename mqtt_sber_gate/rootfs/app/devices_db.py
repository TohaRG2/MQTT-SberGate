import json

import sber_api
from config import read_json_file, write_json_file, VERSION
from converters import rgb_to_sber_hsv
from logger import log_info, log_debug, log_trace, log_deeptrace, log_warning, log_error


class CDevicesDB(object):
    """
    Менеджер локальной базы данных устройств, обрабатывающий сопоставление сущностей
    Home Assistant и категорий/состояний SberDevice.
    """

    def __init__(self, db_file_path):
        """Инициализация базы данных из файла и настройка начального состояния."""
        self.db_file_path = db_file_path
        self.devices_registry = read_json_file(db_file_path)

        # Убеждаемся, что у всех устройств есть флаг 'enabled'
        for entity_id in self.devices_registry:
            if self.devices_registry[entity_id].get('enabled') is None:
                self.devices_registry[entity_id]['enabled'] = False

        self.mqtt_json_devices_list = '{}'
        self.mqtt_json_states_list = '{}'
        self.http_json_devices_list = '{}'

        self.do_http_json_devices_list()

    def generate_new_id(self, prefix):
        """Генерация уникального ID с заданным префиксом."""
        for i in range(1, 99):
            new_id = f"{prefix}_{str(i).zfill(2)}"
            if self.devices_registry.get(new_id) is None:
                return new_id
        return None

    def save_db(self):
        """Сохранение текущей базы данных на диск."""
        write_json_file(self.db_file_path, self.devices_registry)

    def clear_database(self):
        """Удаление всех устройств из базы данных."""
        self.devices_registry = {}
        self.save_db()

    def delete_device(self, entity_id):
        """Удаление устройства из базы данных."""
        if entity_id in self.devices_registry:
            self.devices_registry.pop(entity_id)
            self.save_db()
            log_info(f"Удалено устройство: {entity_id}!")

    def is_device_in_base(self, entity_id):
        """Проверка существования устройства в базе данных."""
        return entity_id in self.devices_registry

    def change_state(self, entity_id, state_key, value):
        """Обновление состояния конкретного атрибута устройства."""
        if entity_id not in self.devices_registry:
            log_warning(f"Устройство id={entity_id} не найдено")
            return

        device = self.devices_registry[entity_id]
        if 'States' not in device:
            log_debug(f"Для устройства id={entity_id} не найдены состояния (States). Создаем.")
            device['States'] = {}

        if state_key not in device['States']:
            log_deeptrace(f"Для устройства id={entity_id} ключ={state_key} не найден. Создаем.")

        device['States'][state_key] = value

    def get_states(self, entity_id):
        """Возвращает все состояния для конкретного устройства."""
        device = self.devices_registry.get(entity_id, {})
        return device.get('States', {})

    def get_state(self, entity_id, state_key):
        """Возвращает значение конкретного состояния устройства."""
        device = self.devices_registry.get(entity_id, {})
        states = device.get('States', {})
        return states.get(state_key)

    def update_device_attributes(self, entity_id, attributes):
        """Обновление нескольких атрибутов существующего устройства."""
        if entity_id in self.devices_registry:
            for key, value in attributes.items():
                self.devices_registry[entity_id][key] = value
            self.save_db()

    def update(self, entity_id, data):
        """Обновление или создание записи устройства с предоставленными данными и значениями по умолчанию."""
        default_attributes = {
            'enabled': False,
            'name': '',
            'default_name': '',
            'nicknames': [],
            'home': '',
            'room': '',
            'groups': [],
            'model_id': '',
            'category': '',
            'hw_version': f'hw:{VERSION}',
            'sw_version': f'sw:{VERSION}',
            'entity_ha': False,
            'entity_type': '',
            'friendly_name': ''
        }

        if entity_id not in self.devices_registry:
            log_info(f"Устройство {entity_id} не найдено. Добавляем новую запись.")
            self.devices_registry[entity_id] = {}
            for key, default_val in default_attributes.items():
                self.devices_registry[entity_id][key] = data.get(key, default_val)

            if data.get('category') == 'scenario_button':
                self.devices_registry[entity_id]['States'] = {'button_event': ''}

        # Обновление новыми данными
        for key, value in data.items():
            self.devices_registry[entity_id][key] = value

        # Убеждаемся, что имя не пустое
        if not self.devices_registry[entity_id].get('name'):
            self.devices_registry[entity_id]['name'] = self.devices_registry[entity_id].get('friendly_name', '')

        self.save_db()

    def do_mqtt_json_devices_list(self):
        """Генерация JSON для публикации конфигурации устройств в Sber MQTT."""
        payload = {'devices': []}

        # Добавляем корневой хаб
        payload['devices'].append({
            "id": "root",
            "name": "Вумный контроллер",
            'hw_version': VERSION,
            'sw_version': VERSION,
            'model': {
                'id': 'ID_root_hub',
                'manufacturer': 'TM',
                'model': 'VHub',
                'description': "HA MQTT SberGate HUB",
                'category': 'hub',
                'features': ['online']
            }
        })

        for entity_id, device in self.devices_registry.items():
            if device.get('enabled', False):
                dev_entry = {
                    'id': entity_id,
                    'name': device.get('name', ''),
                    'default_name': device.get('default_name', ''),
                    'home': device.get('home', 'Мой дом'),
                    'room': device.get('room', ''),
                    'hw_version': device.get('hw_version', ''),
                    'sw_version': device.get('sw_version', '')
                }

                category = device.get('category', 'relay')
                category_features = sber_api.Categories.get(category)

                active_features = []
                if category_features:
                    for feature in category_features:
                        feature_name = feature['name']
                        if feature.get('required', False):
                            active_features.append(feature_name)
                        else:
                            # Добавляем необязательные функции, если они есть в текущих состояниях
                            if feature_name in self.get_states(entity_id):
                                active_features.append(feature_name)

                dev_entry['model'] = {
                    'id': f'ID_{category}',
                    'manufacturer': 'TM',
                    'model': f'Model_{category}',
                    'category': category,
                    'features': active_features
                }
                dev_entry['model_id'] = ''
                payload['devices'].append(dev_entry)

        self.mqtt_json_devices_list = json.dumps(payload)
        log_debug(f'Новый список устройств для MQTT: {self.mqtt_json_devices_list}')
        return self.mqtt_json_devices_list

    def get_default_value_for_feature(self, feature):
        """Возвращает значение по умолчанию на основе типа данных Сбера."""
        data_type = feature['data_type']
        feature_name = feature.get('name', '')

        default_values_by_type = {
            'BOOL': False,
            'INTEGER': 0,
            'ENUM': '',
            'COLOUR': {'red': 255, 'green': 255, 'blue': 255}  # Белый в формате dict
        }

        value = default_values_by_type.get(data_type)
        if value is None:
            log_error(f'Неизвестный тип данных: {data_type}')
            return False

        if feature_name == 'online':
            return True
        return value

    def format_state_for_sber(self, entity_id, feature):
        """Форматирование одного значения состояния для полезной нагрузки Sber MQTT."""
        feature_name = feature['name']
        state_value = self.devices_registry[entity_id]['States'][feature_name]
        data_type = feature['data_type']

        # Сбер ожидает температуру, умноженную на 10
        if feature_name == 'temperature':
            state_value = state_value * 10

        result = {'key': feature_name, 'value': {'type': data_type}}

        if data_type == 'BOOL':
            result['value']['bool_value'] = bool(state_value)
        elif data_type == 'INTEGER':
            result['value']['integer_value'] = int(state_value)
        elif data_type == 'ENUM':
            result['value']['enum_value'] = state_value
        elif data_type == 'COLOUR':
            # COLOUR в Сбере использует HSV формат: h (0-360), s (0-1000), v (100-1000)
            if isinstance(state_value, dict):
                r = state_value.get('red', 255)
                g = state_value.get('green', 255)
                b = state_value.get('blue', 255)

                h_sber, s_sber, v_sber = rgb_to_sber_hsv(r, g, b)

                result['value']['colour_value'] = {
                    'h': h_sber,
                    's': s_sber,
                    'v': v_sber
                }
                log_deeptrace(f"RGB({r},{g},{b}) -> HSV(h={h_sber}, s={s_sber}, v={v_sber})")
            else:
                log_warning(f"ПРЕДУПРЕЖДЕНИЕ: Неверный формат COLOUR для {entity_id}: {state_value}")
                result['value']['colour_value'] = {'h': 0, 's': 0, 'v': 1000}

        log_deeptrace(f"{entity_id}: {result}")
        return result

    def do_mqtt_json_states_list(self, entity_id_list):
        """Генерация JSON для обновлений состояния в Sber MQTT."""
        states_payload = {'devices': {}}

        if not entity_id_list:
            entity_id_list = list(self.devices_registry.keys())

        for entity_id in entity_id_list:
            device = self.devices_registry.get(entity_id)
            if device and device.get('enabled'):
                category = device.get('category', 'relay')
                if not device.get('category'):
                    device['category'] = category

                states_payload['devices'][entity_id] = {}
                features = sber_api.Categories.get(category)

                if features:
                    if 'States' not in device:
                        device['States'] = {}

                    formatted_states = []
                    for feature in features:
                        feature_name = feature['name']
                        current_val = device['States'].get(feature_name)

                        # Обработка отсутствующих обязательных состояний
                        if current_val is None:
                            if feature.get('required', False):
                                log_trace(f'Отсутствует обязательное состояние: {feature_name}')
                                device['States'][feature_name] = self.get_default_value_for_feature(feature)

                        # Добавляем только если значение существует (теперь инициализировано, если обязательно)
                        if device['States'].get(feature_name) is not None:
                            formatted_states.append(self.format_state_for_sber(entity_id, feature))

                            # Сброс событий кнопок после отправки
                            if feature_name == 'button_event':
                                device['States']['button_event'] = ''

                    states_payload['devices'][entity_id]['states'] = formatted_states

        # Возврат к статусу online корневого хаба, если устройства не сообщаются
        if not states_payload['devices']:
            states_payload['devices'] = {
                "root": {"states": [{"key": "online", "value": {"type": "BOOL", "bool_value": True}}]}
            }

        self.mqtt_json_states_list = json.dumps(states_payload)
        log_debug(f"Отправка состояний в Сбер: {self.mqtt_json_states_list[:200]}")
        return self.mqtt_json_states_list

    def do_http_json_devices_list(self):
        """Генерация упрощенного списка устройств для UI/HTTP API."""
        device_list = []
        for entity_id, device in self.devices_registry.items():
            device_info = {
                'id': entity_id,
                'name': device.get('name', ''),
                'default_name': device.get('default_name', ''),
                'nicknames': device.get('nicknames', []),
                'home': device.get('home', ''),
                'room': device.get('room', ''),
                'groups': device.get('groups', []),
                'model_id': device.get('model_id', ''),
                'category': device.get('category', ''),
                'hw_version': device.get('hw_version', ''),
                'sw_version': device.get('sw_version', '')
            }
            device_list.append(device_info)

        self.http_json_devices_list = json.dumps({'devices': device_list})
        return self.http_json_devices_list

    def do_http_json_devices_list_full(self):
        """Возвращает всю базу данных в формате JSON."""
        return json.dumps({'devices': self.devices_registry})
