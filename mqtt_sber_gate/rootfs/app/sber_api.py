import os
import requests
import json
from logger import log
from config import OPTIONS, read_json_file, write_json_file, CATEGORIES_FILE_PATH, update_option

Categories = {}
resCategories = {'categories': []}

def get_sber_headers():
    return {'content-type': 'application/json'}

def get_sber_auth():
    return (OPTIONS.get('sber-mqtt_login'), OPTIONS.get('sber-mqtt_password'))

def fetch_models():
    if not os.path.exists('models.json'):
        log('Файл моделей отсутствует. Получаем...')
        endpoint = OPTIONS.get('sber-http_api_endpoint')
        if not endpoint:
            log('sber-http_api_endpoint is missing')
            return
            
        try:
            SD_Models = requests.get(endpoint + '/v1/mqtt-gate/models', headers=get_sber_headers(),
                                     auth=get_sber_auth())
            if SD_Models.status_code == 200:
                write_json_file('models.json', SD_Models.json())
            else:
                log('ОШИБКА! Запрос models завершился с ошибкой: ' + str(SD_Models.status_code))
        except Exception as e:
            log('Exception fetching models: ' + str(e))

def get_category():
    global Categories
    endpoint = OPTIONS.get('sber-http_api_endpoint')
    
    if not os.path.exists(CATEGORIES_FILE_PATH):
        if not endpoint:
            log('sber-http_api_endpoint is missing, cannot fetch categories')
            return {}

        log('Файл категорий отсутствует. Получаем...')
        Categories = {}
        try:
            SD_Categories = requests.get(endpoint + '/v1/mqtt-gate/categories', headers=get_sber_headers(),
                                         auth=get_sber_auth()).json()
            for id in SD_Categories['categories']:
                log('Получаем опции для котегории!!!: ' + id)
                SD_Features = requests.get(
                    endpoint + '/v1/mqtt-gate/categories/' + id + '/features', headers=get_sber_headers(),
                    auth=get_sber_auth()).json()
                Categories[id] = SD_Features['features']

            write_json_file(CATEGORIES_FILE_PATH, Categories)
        except Exception as e:
            log('Error fetching categories: ' + str(e))
            return {}
    else:
        log('Список категорий получен из файла!!!: ' + CATEGORIES_FILE_PATH)
        Categories = read_json_file(CATEGORIES_FILE_PATH)
    return Categories

def init_categories():
    global Categories, resCategories
    Categories = get_category()

    if Categories.get('categories', False):
        log('Старая версия файла категорий, удаляем.')
        os.remove(CATEGORIES_FILE_PATH)
        log('Повторное получения категорий.')
        Categories = get_category()

    # Получаем список категорий в формате Сбер API для возврата по запросу
    resCategories = {'categories': []}
    for id in Categories:
        resCategories['categories'].append(id)
