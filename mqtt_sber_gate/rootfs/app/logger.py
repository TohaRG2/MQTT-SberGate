import os
from datetime import datetime

LOG_LEVEL_LIST = {'deeptrace': 0, 'trace': 1, 'debug': 2, 'info': 3, 'notice': 4, 'warning': 5, 'error': 6, 'fatal': 7}
LOG_FILE = 'SberGate.log'
LOG_FILE_MAX_SIZE = 1024 * 1024 * 7

# Global log level, default to 0 (deeptrace) but will be updated
log_level = 0

def set_log_level(level_name):
    global log_level
    log_level = LOG_LEVEL_LIST.get(level_name, 3)

def log(s, l=3):
    out_file = open(LOG_FILE, "a", encoding="utf-8")
    
    if l >= log_level:
        dt = datetime.now().strftime("%Y%m%d-%H%M%S.%f") + ': ' + str(s)
        print(dt)
        out_file.write(dt + '\r\n')

    out_file.close()

def check_log_file_size():
    if os.path.isfile(LOG_FILE):
        if os.path.getsize(LOG_FILE) > LOG_FILE_MAX_SIZE:
            os.remove(LOG_FILE)
