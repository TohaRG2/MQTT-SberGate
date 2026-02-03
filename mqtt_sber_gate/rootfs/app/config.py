import json
import os
from logger import log

VERSION = '2.0.1'
base_dir = os.path.dirname(os.path.abspath(__file__))

# В Home Assistant конфигурация аддона (options.json) всегда находится в /data
# Остальные файлы (devices.json) также лучше хранить в /data для персистентности
if os.path.exists('/data'):
    DATA_DIR = '/data'
else:
    DATA_DIR = base_dir

OPTIONS_FILE_PATH = os.path.join(DATA_DIR, 'options.json')
DEVICES_DB_FILE_PATH = os.path.join(DATA_DIR, 'devices.json')
CATEGORIES_FILE_PATH = os.path.join(DATA_DIR, 'categories.json')

OPTIONS = {}

def read_json_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = f.read()
        result = json.loads(data)
    except Exception as e:
        result = {}
        log(f'!!! Ошибка чтения или разбора файла {file_path}: {e}')
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
    if current_value is None:
        log('В настройках отсутствует параметр: ' + key + ' (добавляю.)')
    if current_value != value:
        OPTIONS[key] = value
        log('В настройках изменился параметр: ' + key + ' с ' + str(current_value) + ' на ' + str(value) + ' (обновляю и сохраняю).')
        write_json_file(OPTIONS_FILE_PATH, OPTIONS)

# Auto-load options on import
load_options()
