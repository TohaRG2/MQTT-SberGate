import json
import ssl
import paho.mqtt.client as mqtt
from logger import log
from config import update_option

class SberMQTTClient:
    """
    Клиент для взаимодействия с MQTT-брокером Сбера.
    Обеспечивает получение команд и отправку состояний устройств.
    """
    def __init__(self, device_database, config_options):
        """Инициализация MQTT клиента Сбера."""
        self.device_database = device_database
        self.config_options = config_options
        self.ha_client = None  # Устанавливается через set_ha_client
        self.mqtt_client = mqtt.Client()
        
        # Структура топиков SberDevice MQTT
        self.sber_user_login = self.config_options.get('sber-mqtt_login', 'UNKNOWN_USER')
        if self.sber_user_login == 'UNKNOWN_USER':
            log("КРИТИЧЕСКАЯ ОШИБКА: 'sber-mqtt_login' отсутствует в конфигурации!", 6)
            
        self.root_topic = f"sberdevices/v1/{self.sber_user_login}"
        self.downlink_topic = f"{self.root_topic}/down"
        self.uplink_topic = f"{self.root_topic}/up"
        
        self.setup_mqtt_client()

    def set_ha_client(self, ha_client_instance):
        """Связывание с клиентом Home Assistant."""
        self.ha_client = ha_client_instance

    def on_connect(self, client, userdata, flags, reason_code):
        """Обработчик успешного подключения к брокеру."""
        if reason_code == 0:
            log(f"Успешное подключение к брокеру SberDevices (rc: {reason_code})")
            # Подписка на команды и обновления конфигурации
            client.subscribe(f"{self.downlink_topic}/#", qos=0)
            client.subscribe("sberdevices/v1/__config", qos=0)
        else:
            log(f"Ошибка подключения к брокеру SberDevices (rc: {reason_code})", 6)

    def on_disconnect(self, client, userdata, reason_code):
        """Обработчик отключения от брокера."""
        if reason_code != 0:
            log(f"Неожиданное отключение от MQTT (rc: {reason_code}). Автореконнект включен.", 6)

    def on_message_received(self, client, userdata, message):
        """Общий обработчик входящих MQTT сообщений."""
        log(f"MQTT сообщение: {message.topic} (QoS: {message.qos}) -> {message.payload}", 0)

    def on_subscribe_success(self, client, userdata, mid, granted_qos):
        """Обработчик успешной подписки на топик."""
        log(f"Подписка успешна (MID: {mid}, QoS: {granted_qos})")

    def send_status(self, status_payload):
        """Отправка текущего статуса устройств в Сбер."""
        status_topic = f"{self.uplink_topic}/status"
        self.mqtt_client.publish(status_topic, status_payload, qos=0)

    def handle_command_message(self, client, userdata, message):
        """Обработка команд управления устройствами от Сбера."""
        try:
            command_data = json.loads(message.payload)
        except json.JSONDecodeError:
            log(f"Ошибка декодирования команды: {message.payload}", 6)
            return

        log(f"Получена команда от Сбера через MQTT: {command_data}", 2)
        
        last_entity_id = None
        for entity_id, device_data in command_data.get('devices', {}).items():
            last_entity_id = entity_id
            state_changes = {}
            
            for state_item in device_data.get('states', []):
                key = state_item['key']
                value_wrapper = state_item['value']
                value_type = value_wrapper.get('type', '')
                
                new_value = None
                if value_type == 'BOOL':
                    new_value = value_wrapper.get('bool_value', False)
                elif value_type == 'INTEGER':
                    new_value = value_wrapper.get('integer_value', 0)
                elif value_type == 'ENUM':
                    new_value = value_wrapper.get('enum_value', '')
                elif value_type == 'COLOUR':
                    # Сбер отправляет цвет в формате HSV: h (0-360), v (0-1000)
                    import colorsys
                    colour_value = value_wrapper.get('colour_value', {})
                    h = colour_value.get('h', 0) / 360.0  # Конвертируем из градусов в 0-1
                    v = colour_value.get('v', 1000) / 1000.0  # Конвертируем из 0-1000 в 0-1
                    s = 1.0  # Saturation = 100% (полная насыщенность)
                    
                    # Конвертируем HSV в RGB
                    r, g, b = colorsys.hsv_to_rgb(h, s, v)
                    new_value = {
                        'red': int(r * 255),
                        'green': int(g * 255),
                        'blue': int(b * 255)
                    }
                    log(f"HSV(h={colour_value.get('h')}, v={colour_value.get('v')}) -> RGB({new_value['red']},{new_value['green']},{new_value['blue']})")

                # Отслеживаем, изменилось ли значение на самом деле
                current_value = self.device_database.get_state(entity_id, key)
                state_changes[key] = (current_value != new_value)

                # Обновляем локальную базу данных
                self.device_database.change_state(entity_id, key, new_value)
                
                # Устанавливаем ожидаемое состояние для фильтрации эха
                device_info = self.device_database.devices_registry.get(entity_id, {})
                device_info['_expected_mqtt_state'] = new_value

            # Передаем команду в Home Assistant
            if self.ha_client:
                device_info = self.device_database.devices_registry.get(entity_id, {})
                if device_info.get('entity_type') == 'climate':
                    self.ha_client.set_climate_temperature(entity_id, state_changes)
                elif device_info.get('entity_ha', False):
                    self.ha_client.toggle_device_state(entity_id)
                else:
                    log(f"Устройство не найдено или не управляется HA: {entity_id}", 3)
        
        # Отправляем подтверждение с обновленным статусом
        if last_entity_id:
            self.send_status(self.device_database.do_mqtt_json_states_list([last_entity_id]))

    def handle_status_request(self, client, userdata, message):
        """Обработка запроса текущего состояния устройств."""
        try:
            request_data = json.loads(message.payload)
            device_ids = request_data.get('devices', [])
        except:
            device_ids = []
            
        log(f"Получен запрос статуса для: {device_ids}",2)
        response_payload = self.device_database.do_mqtt_json_states_list(device_ids)
        self.send_status(response_payload)

    def handle_config_request(self, client, userdata, message):
        """Обработка запроса конфигурации устройств."""
        log("Получен запрос конфигурации устройств")
        config_payload = self.device_database.do_mqtt_json_devices_list()
        self.mqtt_client.publish(f"{self.uplink_topic}/config", config_payload, qos=0)

    def handle_global_config(self, client, userdata, message):
        """Обработка глобальной конфигурации от Сбера."""
        try:
            global_config = json.loads(message.payload)
            endpoint = global_config.get('http_api_endpoint', '')
            if endpoint:
                update_option('sber-http_api_endpoint', endpoint)
        except Exception as e:
            log(f"Ошибка обработки глобальной конфигурации: {e}", 6)

    def on_mqtt_error(self, client, userdata, message):
        """Обработчик ошибок MQTT."""
        log(f"Ошибка Sber MQTT: {message.topic} -> {message.payload}", 6)

    def setup_mqtt_client(self):
        """Настройка MQTT клиента: коллбэки, авторизация, TLS."""
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_subscribe = self.on_subscribe_success
        self.mqtt_client.on_message = self.on_message_received
        self.mqtt_client.on_disconnect = self.on_disconnect
        
        # Коллбэки для конкретных топиков
        self.mqtt_client.message_callback_add("sberdevices/v1/__config", self.handle_global_config)
        self.mqtt_client.message_callback_add(f"{self.downlink_topic}/errors", self.on_mqtt_error)
        self.mqtt_client.message_callback_add(f"{self.downlink_topic}/commands", self.handle_command_message)
        self.mqtt_client.message_callback_add(f"{self.downlink_topic}/status_request", self.handle_status_request)
        self.mqtt_client.message_callback_add(f"{self.downlink_topic}/config_request", self.handle_config_request)

        # Авторизация и TLS
        mqtt_user = self.config_options.get('sber-mqtt_login', '')
        mqtt_pass = self.config_options.get('sber-mqtt_password', '')
        
        if mqtt_user and mqtt_pass:
            self.mqtt_client.username_pw_set(mqtt_user, mqtt_pass)
        else:
            log("ПРЕДУПРЕЖДЕНИЕ: Данные MQTT отсутствуют в конфигурации!", 5)
            
        # Сбер использует специфические сертификаты, отключаем проверку для совместимости
        self.mqtt_client.tls_set(certfile=None, keyfile=None, cert_reqs=ssl.CERT_NONE, tls_version=None)
        self.mqtt_client.tls_insecure_set(True)

    def start(self):
        """Подключение к брокеру и запуск цикла обработки сообщений."""
        broker_host = self.config_options.get('sber-mqtt_broker', 'mqtt.sberdevices.ru')
        broker_port = self.config_options.get('sber-mqtt_broker_port', 8883)
        log(f"Подключение к брокеру Sber MQTT: {broker_host}:{broker_port}")
        
        try:
            self.mqtt_client.connect(broker_host, broker_port, keepalive=60)
            self.mqtt_client.loop_start()
        except Exception as e:
            log(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось подключиться к Sber MQTT: {e}", 6)

    def publish_config(self):
        """Публикация конфигурации всех включенных устройств в Сбер."""
        config_payload = self.device_database.do_mqtt_json_devices_list()
        self.mqtt_client.publish(f"{self.uplink_topic}/config", config_payload, qos=0)
        log("Конфигурация устройств опубликована в Sber MQTT")
