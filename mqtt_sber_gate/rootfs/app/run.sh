#!/usr/bin/with-contenv bashio

# Если в /data есть новая версия файла, копируем её в /app
if [ -f /data/sber-gate.py ]; then
    echo "Found /data/sber-gate.py, copying to /app..."
    cp /data/sber-gate.py /app/sber-gate.py
fi

# запуск скрипта
while true; do
    python3 /app/sber-gate.py
done
