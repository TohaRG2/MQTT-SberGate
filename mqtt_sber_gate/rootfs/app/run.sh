#!/usr/bin/with-contenv bashio

CUSTOM_DIR="/share"
APP_DIR="/app"

# Копируем все Python-файлы из /share в /app, если они есть
if ls "$CUSTOM_DIR"/*.py >/dev/null 2>&1; then
    echo "Найдены кастомные .py файлы в $CUSTOM_DIR. Копирование в $APP_DIR..."
    cp "$CUSTOM_DIR"/*.py "$APP_DIR"/
else
    echo "Нет кастомных .py файлов в $CUSTOM_DIR, используем встроенные версии"
fi

# Запуск основного скрипта
while true; do
    python3 "$APP_DIR/sber-gate.py"
    echo "Скрипт остановлен. Перезапуск через 2 секунды..."
    sleep 2
done