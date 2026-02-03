# MQTT-SberGate
## MQTT SberGate SberDevice IoT Agent for Home Assistant

Агент представляет собой прослойку между облаком Sber и HomeAssistant (HA).
Его задача взять из HA нужные устройства, отобразить их в облаке Sber и отслеживать
изменения в облаке с последующей передачей в HA.
Основан на коде агента от [JanchEwgen](https://github.com/JanchEwgen/MQTT-SberGate).

## Первоначальные настройки.

Для работы агента необходима [регистрация в SberStudio](https://developers.sber.ru/studio/workspaces/).

Требуется создать интеграцию и получить регистрационные данные для агента (sber-mqtt_login, 
sber-mqtt_password) для подключения к облаку Сбера и пробросу туда устройств из HA.

Также необходим токен для управления HA. Очень рекомендую завести для этого отдельного пользователя
в Home Assistant. Для получения заходим в профиль пользователя и создаём долгосрочный токен
доступа (ha-api_token)


## Полезные Ссылки.

Для работы с MQTT используется [Eclipse Paho™ MQTT Python Client](https://github.com/eclipse/paho.mqtt.python)

[Регистрация пространства в Studio](https://developers.sber.ru/docs/ru/smarthome/space/registration)

[Создание проекта интеграции в Studio](https://developers.sber.ru/docs/ru/smarthome/mqtt-diy/create-mqtt-diy-integration-project)

[Авторизация контроллера в облаке Sber](https://developers.sber.ru/docs/ru/smarthome/mqtt-diy/controller-authorization)

[Как работает интеграция Sber](https://developers.sber.ru/docs/ru/smarthome/mqtt-diy/integration-scheme)

[Создание интеграции Sber](https://developers.sber.ru/docs/ru/smarthome/mqtt-diy/create-mqtt-diy-integration)

[HA REST API](https://developers.home-assistant.io/docs/api/rest)

[HA WebSocket API](https://developers.home-assistant.io/docs/api/websocket)
