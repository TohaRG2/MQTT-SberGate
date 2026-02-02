import json
import os
from logger import log

VERSION = '1.0.17'
base_dir = os.path.dirname(os.path.abspath(__file__))
OPTIONS_FILE_PATH = os.path.join(base_dir, 'options.json')
DEVICES_DB_FILE_PATH = os.path.join(base_dir, 'devices.json')
CATEGORIES_FILE_PATH = os.path.join(base_dir, 'categories.json')

OPTIONS = {}

def read_json_file(file_path):
    try:
        data = open(file_path, 'r', encoding='utf-8').read()
        result = json.loads(data)
    except:
        result = {}
        log('!!! Неверная конфигурация в файле: ' + file_path)
    return result

def write_json_file(file_path, data):
    with open(file_path, "w", encoding='utf-8') as out_file:
        json.dump(data, out_file, ensure_ascii=False, indent=4)

def load_options():
    global OPTIONS
    OPTIONS.update(read_json_file(OPTIONS_FILE_PATH))
    return OPTIONS

def update_option(key, value):
    current_value = OPTIONS.get(key, None)
    if (current_value is None):
        log('В настройках отсутствует параметр: ' + key + ' (добавляю.)')
    if (current_value != value):
        OPTIONS[key] = value
        log('В настройках изменился параметр: ' + key + ' с ' + str(current_value) + ' на ' + str(value) + ' (обновляю и сохраняю).')
        write_json_file(OPTIONS_FILE_PATH, OPTIONS)

# Auto-load options on import
load_options()
