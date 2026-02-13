import json
from logger import log
from config import read_json_file, write_json_file, VERSION
import sber_api

class CDevicesDB(object):
    """docstring"""

    def __init__(self, f):
        """Constructor 'devices.json'"""
        self.fDB = f
        self.DB = read_json_file(f)
        for id in self.DB:
            if self.DB[id].get('enabled', None) is None:
                self.DB[id]['enabled'] = False

        self.mqtt_json_devices_list = '{}'
        self.mqtt_json_states_list = '{}'
        self.http_json_devices_list = '{}'
        #      self.do_mqtt_json_devices_list()
        #      self.do_mqtt_json_states_list({})
        self.do_http_json_devices_list()

    def new_id(self, a):
        r = ''
        for i in range(1, 99):
            r = a + '_' + ('00' + str(i))[-2:]
            if self.DB.get(r, None) is None:
                return r
        return None

    def save_db(self):
        write_json_file(self.fDB, self.DB)
    #      self.do_http_json_devices_list()

    def clear(self, d):
        self.DB = {}
        self.save_db()

    def dev_add(self):
        print('device_Add')

    def dev_del(self, id):
        self.DB.pop(id, None)
        self.save_db()
        log('Delete Device: ' + id + '!')

    def dev_in_base(self, id):
        if self.DB.get(id, None) is None:
            return False
        else:
            return True

    def change_state(self, id, key, value):
        if self.DB.get(id, None) is None:
            log('Device id=' + str(id) + ' not found')
            return
        if self.DB[id].get('States', None) is None:
            log('Device id=' + str(id) + ' States not Found. Create.')
            self.DB[id]['States'] = {}
        if self.DB[id]['States'].get(key, None) is None:
            log('Device id=' + str(id) + ' key=' + str(key) + ' not Found. Create.')
        self.DB[id]['States'][key] = value

    #      self.do_mqtt_json_states_list([id])

    def get_states(self, id):
        d = self.DB.get(id, {})
        return d.get('States', {})

    def get_state(self, id, key):
        d = self.DB.get(id, {})
        s = d.get('States', {})
        return s.get(key, None)

    def update_only(self, device_id, attributes):
        if self.DB.get(device_id) is not None:
            for key, value in attributes.items():
                self.DB[device_id][key] = value
            self.save_db()

    def update(self, updated_id, d):
        # задаем дефолтные значения для полей записи в базе
        fl = {'enabled': False,
              'name': '',
              'default_name': '',
              'nicknames': [],
              'home': '',
              'room': '',
              'groups': [],
              'model_id': '',
              'category': '',
              'hw_version': 'hw:' + VERSION,
              'sw_version': 'sw:' + VERSION,
              'entity_ha': False,
              'entity_type': '',
              'friendly_name': ''}
        if self.DB.get(updated_id, None) is None:
            log('Device ' + updated_id + ' Not Found. Adding')
            self.DB[updated_id] = {}
            for k, v in fl.items():
                self.DB[updated_id][k] = d.get(k, v)
            if d['category'] == 'scenario_button':
                self.DB[updated_id]['States'] = {'button_event': ''}

        for k, v in d.items():
            self.DB[updated_id][k] = d.get(k, v)
        if self.DB[updated_id]['name'] == '':
            self.DB[updated_id]['name'] = self.DB[updated_id]['friendly_name']
        self.save_db()

    def device_states_mqtt_sber(self, id):
        d = self.DB.get(id, None)
        #      log(d)
        r = []
        if d is None:
            log('Запрошен несуществующий объект: ' + id)
            return r
        s = d.get('States', None)
        if s is None:
            log('У объекта: ' + id + 'отсутствует информация о состояниях')
            return r
        if d['category'] == 'relay':
            v = s.get('on_off', False)
            r.append({'key': 'online', 'value': {"type": "BOOL", "bool_value": True}})
            r.append({'key': 'on_off', 'value': {"type": "BOOL", "bool_value": v}})
        if d['category'] == 'sensor_temp':
            r.append({'key': 'online', 'value': {"type": "BOOL", "bool_value": True}})
            if 'temperature' in s:
                v = round(s.get('temperature', 0) * 10)
                r.append({'key': 'temperature', 'value': {"type": "INTEGER", "integer_value": v}})
            if 'humidity' in s:
                v = round(s.get('humidity', 0))
                r.append({'key': 'humidity', 'value': {"type": "INTEGER", "integer_value": v}})
            if 'air_pressure' in s:
                v = round(s.get('air_pressure', 0))
                r.append({'key': 'air_pressure', 'value': {"type": "INTEGER", "integer_value": v}})

        if d['category'] == 'scenario_button':
            v = s.get('button_event', 'click')
            r.append({'key': 'online', 'value': {"type": "BOOL", "bool_value": True}})
            r.append({'key': 'button_event', 'value': {"type": "ENUM", "enum_value": v}})

        if d['category'] == 'hvac_ac':
            v = round(s.get('temperature', 20) * 10)
            vv = round(s.get('hvac_temp_set', 20) * 10)
            r.append({'key': 'online', 'value': {"type": "BOOL", "bool_value": True}})
            r.append({'key': 'on_off', 'value': {"type": "BOOL", "bool_value": True}})
            r.append({'key': 'temperature', 'value': {"type": "INTEGER", "integer_value": v}})
            r.append({'key': 'hvac_temp_set', 'value': {"type": "INTEGER", "integer_value": vv}})

        if d['category'] == 'hvac_radiator':
            #         log('hvac')
            v = round(s.get('temperature', 0) * 10)
            r.append({'key': 'online', 'value': {"type": "BOOL", "bool_value": True}})
            r.append({'key': 'on_off', 'value': {"type": "BOOL", "bool_value": True}})
            r.append({'key': 'temperature', 'value': {"type": "INTEGER", "integer_value": v}})
            r.append({'key': 'hvac_temp_set', 'value': {"type": "INTEGER", "integer_value": 30}})
        #         log(r)

        #      for k,v in s.items():
        #         log(k)
        #         if (isinstance(v,bool)):
        #            o={'key':k,'value':{"type": "BOOL", "bool_value": v}}
        #         elif (isinstance(v, int)):
        #            o={'key':k,'value':{"type": "INTEGER", "integer_value": v}}
        #         else:
        #            log(v)
        #            o={'key':k,'value':{"type": "BOOL", "bool_value": False}}
        #         r.append(o)
        return r

    def do_mqtt_json_devices_list(self):
        dev = {'devices': []}
        dev['devices'].append({"id": "root", "name": "Вумный контроллер", 'hw_version': VERSION, 'sw_version': VERSION})
        dev['devices'][0]['model'] = {'id': 'ID_root_hub', 'manufacturer': 'TM', 'model': 'VHub',
                                      'description': "HA MQTT SberGate HUB", 'category': 'hub', 'features': ['online']}
        for k, v in self.DB.items():
            if v.get('enabled', False):
                d = {'id': k, 'name': v.get('name', ''), 'default_name': v.get('default_name', '')}
                d['home'] = v.get('home', 'Мой дом')
                d['room'] = v.get('room', '')
                #            d['groups']=['Спальня']
                d['hw_version'] = v.get('hw_version', '')
                d['sw_version'] = v.get('sw_version', '')
                dev_cat = v.get('category', 'relay')
                
                c = sber_api.Categories.get(dev_cat)
                
                f = []
                if c:
                    for ft in c:
                        if ft.get('required', False):
                            f.append(ft['name'])
                        else:
                            for st in self.get_states(k):
                                if ft['name'] == st:
                                    f.append(ft['name'])

                d['model'] = {'id': 'ID_' + dev_cat, 'manufacturer': 'TM', 'model': 'Model_' + dev_cat,
                              'category': dev_cat, 'features': f}
                #            log(d['model'])
                d['model_id'] = ''
                dev['devices'].append(d)
        self.mqtt_json_devices_list = json.dumps(dev)
        log('New Devices List for MQTT: ' + self.mqtt_json_devices_list, 1)
        return self.mqtt_json_devices_list

    def default_value(self, feature):
        t = feature['data_type']
        dv_dict = {
            'BOOL': False,
            'INTEGER': 0,
            'ENUM': ''
        }
        v = dv_dict.get(t, None)
        if v is None:
            log('Неизвестный тип даных: ' + t)
            return False
        else:
            if feature['name'] == 'online':
                return True
            else:
                return v

    def state_value(self, id, feature):
        # {'key':'online','value':{"type": "BOOL", "bool_value": True}}
        State = self.DB[id]['States'][feature['name']]
        if feature['name'] == 'temperature':
            State = State * 10
        if feature['data_type'] == 'BOOL':
            r = {'key': feature['name'], 'value': {'type': 'BOOL', 'bool_value': bool(State)}}
        if feature['data_type'] == 'INTEGER':
            r = {'key': feature['name'], 'value': {'type': 'INTEGER', 'integer_value': int(State)}}
        if feature['data_type'] == 'ENUM':
            r = {'key': feature['name'], 'value': {'type': 'ENUM', 'enum_value': State}}
        log(id + ': ' + str(r), 0)
        return r

    def do_mqtt_json_states_list(self, dl):
        d_stat = {'devices': {}}
        if len(dl) == 0:
            dl = self.DB.keys()
        for id in dl:
            device = self.DB.get(id, None)
            if not (device is None):
                if device['enabled']:
                    device_category = device.get('category', None)
                    if device_category is None:
                        device_category = 'relay'
                        self.DB[id]['category'] = device_category
                    d_stat['devices'][id] = {}
                    features = sber_api.Categories.get(device_category)
                    if features:
                        if self.DB[id].get('States', None) is None:
                            self.DB[id]['States'] = {}
                        r = []
                        for ft in features:
                            state_value = self.DB[id]['States'].get(ft['name'], None)
                            if state_value is None:
                                if ft.get('required', False):
                                    log('отсутствует обязательное состояние сущности: ' + ft['name'])
                                    self.DB[id]['States'][ft['name']] = self.default_value(ft)
                            if not (self.DB[id]['States'].get(ft['name'], None) is None):
                                r.append(self.state_value(id, ft))
                                if ft['name'] == 'button_event':
                                    self.DB[id]['States']['button_event'] = ''
                        d_stat['devices'][id]['states'] = r
        #               if (s is None):
        #                  log('У объекта: '+id+'отсутствует информация о состояниях')
        #                  self.DB[id]['States']={}
        #                  self.DB[id]['States']['online']=True
        #               DStat['devices'][id]['states']=self.DeviceStates_mqttSber(id)

        if len(d_stat['devices']) == 0:
            d_stat['devices'] = {"root": {"states": [{"key": "online", "value": {"type": "BOOL", "bool_value": True}}]}}
        self.mqtt_json_states_list = json.dumps(d_stat)
        log(f"Отправка состояний в Sber: {self.mqtt_json_states_list}", 1)
        return self.mqtt_json_states_list

    def do_http_json_devices_list(self):
        Dev = {}
        Dev['devices'] = []
        x = []
        for k, v in self.DB.items():
            r = {}
            r['id'] = k
            r['name'] = v.get('name', '')
            r['default_name'] = v.get('default_name', '')
            r['nicknames'] = v.get('nicknames', [])
            r['home'] = v.get('home', '')
            r['room'] = v.get('room', '')
            r['groups'] = v.get('groops', [])
            r['model_id'] = v['model_id']
            r['category'] = v.get('category', '')
            r['hw_version'] = v.get('hw_version', '')
            r['sw_version'] = v.get('sw_version', '')
            x.append(r)
            Dev['devices'].append(r)
        self.http_json_devices_list = json.dumps({'devices': x})
        return self.http_json_devices_list

    def do_http_json_devices_list_2(self):
        return json.dumps({'devices': self.DB})
