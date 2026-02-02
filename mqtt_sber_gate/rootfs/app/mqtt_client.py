import json
import ssl
import paho.mqtt.client as mqtt
from logger import log
from config import update_option

class SberMQTTClient:
    def __init__(self, device_database, config_options):
        self.device_database = device_database
        self.config_options = config_options
        self.ha_client = None  # Will be set via set_ha_client
        self.mqtt_client = mqtt.Client()
        
        # SberDevice MQTT Topic Structure
        self.sber_user_login = self.config_options.get('sber-mqtt_login', 'UNKNOWN_USER')
        if self.sber_user_login == 'UNKNOWN_USER':
            log("CRITICAL ERROR: 'sber-mqtt_login' is missing in configuration!", 6)
            
        self.root_topic = f"sberdevices/v1/{self.sber_user_login}"
        self.downlink_topic = f"{self.root_topic}/down"
        self.uplink_topic = f"{self.root_topic}/up"
        
        self.setup_mqtt_client()

    def set_ha_client(self, ha_client_instance):
        self.ha_client = ha_client_instance

    def on_connect(self, client, userdata, flags, reason_code):
        if reason_code == 0:
            log(f"Successfully connected to SberDevices Broker (rc: {reason_code})")
            # Subscribe to commands and config updates
            client.subscribe(f"{self.downlink_topic}/#", qos=0)
            client.subscribe("sberdevices/v1/__config", qos=0)
        else:
            log(f"Failed to connect to SberDevices Broker (rc: {reason_code})", 6)

    def on_disconnect(self, client, userdata, reason_code):
        if reason_code != 0:
            log(f"Unexpected MQTT disconnection (rc: {reason_code}). Auto-reconnect enabled.", 6)

    def on_message_received(self, client, userdata, message):
        log(f"MQTT Message: {message.topic} (QoS: {message.qos}) -> {message.payload}", 0)

    def on_subscribe_success(self, client, userdata, mid, granted_qos):
        log(f"Subscription successful (MID: {mid}, QoS: {granted_qos})")

    def send_status(self, status_payload):
        status_topic = f"{self.uplink_topic}/status"
        self.mqtt_client.publish(status_topic, status_payload, qos=0)

    def handle_command_message(self, client, userdata, message):
        try:
            command_data = json.loads(message.payload)
        except json.JSONDecodeError:
            log(f"Error decoding command payload: {message.payload}", 6)
            return

        log(f"Received Sber MQTT Command: {command_data}")
        
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

                # Track if value actually changed
                current_value = self.device_database.DB.get(entity_id, {}).get(key)
                state_changes[key] = (current_value != new_value)

                # Update local database
                self.device_database.change_state(entity_id, key, new_value)

            # Forward command to Home Assistant
            if self.ha_client:
                device_info = self.device_database.DB.get(entity_id, {})
                if device_info.get('entity_type') == 'climate':
                    self.ha_client.set_climate_temperature(entity_id, state_changes)
                elif device_info.get('entity_ha', False):
                    self.ha_client.toggle_device_state(entity_id)
                else:
                    log(f"Device not found or not managed by HA: {entity_id}", 3)
        
        # Respond with updated status
        if last_entity_id:
            self.send_status(self.device_database.do_mqtt_json_states_list([last_entity_id]))

    def handle_status_request(self, client, userdata, message):
        try:
            request_data = json.loads(message.payload)
            device_ids = request_data.get('devices', [])
        except:
            device_ids = []
            
        log(f"Received status request for: {device_ids}")
        response_payload = self.device_database.do_mqtt_json_states_list(device_ids)
        self.send_status(response_payload)

    def handle_config_request(self, client, userdata, message):
        log("Received configuration request")
        config_payload = self.device_database.do_mqtt_json_devices_list()
        self.mqtt_client.publish(f"{self.uplink_topic}/config", config_payload, qos=0)

    def handle_global_config(self, client, userdata, message):
        try:
            global_config = json.loads(message.payload)
            endpoint = global_config.get('http_api_endpoint', '')
            if endpoint:
                update_option('sber-http_api_endpoint', endpoint)
        except Exception as e:
            log(f"Error handling global config: {e}", 6)

    def on_mqtt_error(self, client, userdata, message):
        log(f"Sber MQTT Error: {message.topic} -> {message.payload}", 6)

    def setup_mqtt_client(self):
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_subscribe = self.on_subscribe_success
        self.mqtt_client.on_message = self.on_message_received
        self.mqtt_client.on_disconnect = self.on_disconnect
        
        # Topic-specific callbacks
        self.mqtt_client.message_callback_add("sberdevices/v1/__config", self.handle_global_config)
        self.mqtt_client.message_callback_add(f"{self.downlink_topic}/errors", self.on_mqtt_error)
        self.mqtt_client.message_callback_add(f"{self.downlink_topic}/commands", self.handle_command_message)
        self.mqtt_client.message_callback_add(f"{self.downlink_topic}/status_request", self.handle_status_request)
        self.mqtt_client.message_callback_add(f"{self.downlink_topic}/config_request", self.handle_config_request)

        # Authentication and TLS
        mqtt_user = self.config_options.get('sber-mqtt_login', '')
        mqtt_pass = self.config_options.get('sber-mqtt_password', '')
        
        if mqtt_user and mqtt_pass:
            self.mqtt_client.username_pw_set(mqtt_user, mqtt_pass)
        else:
            log("WARNING: MQTT credentials missing in config!", 5)
            
        # Sber uses self-signed or specific certs, disable verification if requested
        self.mqtt_client.tls_set(certfile=None, keyfile=None, cert_reqs=ssl.CERT_NONE, tls_version=None)
        self.mqtt_client.tls_insecure_set(True)

    def start(self):
        broker_host = self.config_options.get('sber-mqtt_broker', 'mqtt.sberdevices.ru')
        broker_port = self.config_options.get('sber-mqtt_broker_port', 8883)
        log(f"Connecting to Sber MQTT Broker: {broker_host}:{broker_port}")
        
        try:
            self.mqtt_client.connect(broker_host, broker_port, keepalive=60)
            self.mqtt_client.loop_start()
        except Exception as e:
            log(f"CRITICAL ERROR: Failed to connect to Sber MQTT: {e}", 6)

    def publish_config(self):
        config_payload = self.device_database.do_mqtt_json_devices_list()
        self.mqtt_client.publish(f"{self.uplink_topic}/config", config_payload, qos=0)
        log("Device configuration published to Sber MQTT")
