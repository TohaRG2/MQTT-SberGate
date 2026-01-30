#!/usr/bin/with-contenv bashio

CUSTOM_FILE="/share/sber-gate.py"
APP_FILE="/app/sber-gate.py"

# Если в /share есть кастомный файл — подменяем
if [ -f "$CUSTOM_FILE" ]; then
    echo "Custom $CUSTOM_FILE found, copying to $APP_FILE ..."
    cp "$CUSTOM_FILE" "$APP_FILE"
else
    echo "No custom script in /share, using built-in version"
fi

# запуск скрипта
while true; do
    python3 "$APP_FILE"
    echo "Script stopped. Restarting in 2s..."
    sleep 2
done