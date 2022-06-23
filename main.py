import logging
from aiogram.utils.executor import start_polling

from bot import dp


logging.basicConfig(level=logging.DEBUG, filename='debug.log')


if __name__ == '__main__':
    start_polling(dp)
