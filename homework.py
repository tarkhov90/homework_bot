import os
import sys
import requests
import telegram
import time
import logging
import json

from http import HTTPStatus
from dotenv import load_dotenv
from exceptions import (ResponseStatusAPINot200,
                        NotSendingMessageError,
                        NotKeysError,
                        NotForSendingError)


load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

MONTH_AGO = 2678400
RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def send_message(bot, message):
    """Отправляет сообщение в Telegram чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.info('Сообщение отправлено!')
    except NotSendingMessageError as error:
        logging.debug(f'Бот не смог отправить сообщение: {error}')
        raise NotSendingMessageError


def get_api_answer(current_timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса."""
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    try:
        api_answer = requests.get(ENDPOINT, headers=HEADERS, params=params)
        if api_answer.status_code == HTTPStatus.UNAUTHORIZED:
            logging.critical('<PRACTICUM_TOKEN> указан неверно')
            raise KeyError('<PRACTICUM_TOKEN> указан неверно')
        if api_answer.status_code != HTTPStatus.OK:
            logging.debug(
                f'API недоступен, код ошибки: {api_answer.status_code}'
            )
            raise ResponseStatusAPINot200(
                f'API недоступен, код ошибки: {api_answer.status_code}'
            )
        return api_answer.json()
    except ConnectionError:
        logging.critical('Ошибка соединения')
    except json.decoder.JSONDecodeError:
        logging.debug('Ошибка формирования в JSON')


def check_response(response):
    """Проверяет ответ API на корректность."""
    if not isinstance(response, dict):
        logging.error('Oтвет API не является словарём')
        raise TypeError('Oтвет API не является словарём')

    homeworks = response.get('homeworks')
    current_date = response.get('current_date')
    if not (homeworks and current_date):
        logging.debug('Нет новых данных по ключам'
                      '<homeworks> или <current_date>')
        raise NotKeysError
    return homeworks


def parse_status(homeworks):
    """Извлекает из информации о конкретной.
    домашней работе статус этой работы.
    """
    if 'homework_name' not in homeworks:
        message = 'Нет ключа homework_name'
    homework_status = homeworks.get('status')
    homework_name = homeworks.get('homework_name')
    try:
        verdict = HOMEWORK_STATUSES[homework_status]
        return f'Изменился статус проверки работы "{homework_name}". {verdict}'
    except KeyError:
        logging.error(message)
        raise KeyError(message)


def check_tokens():
    """Проверяет доступность переменных окружения."""
    tokens_status = all([TELEGRAM_TOKEN, PRACTICUM_TOKEN, TELEGRAM_CHAT_ID])
    return tokens_status


def main():
    """Основная логика работы бота."""
    logging.basicConfig(
        level=logging.DEBUG,
        handlers=[
            logging.FileHandler('my_logging.log', 'w', encoding='utf8'),
            logging.StreamHandler(sys.stdout),
        ],
        format=('%(asctime)s - '
                '%(levelname)s - '
                '%(message)s - '
                '%(name)s - '),
    )

    if check_tokens() is True:
        logging.info('Все токены доступны')
    else:
        logging.critical('Нет нужных токенов')
        raise KeyError('Нет нужных токенов')

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time() - MONTH_AGO)
    last_message = ''
    last_homework = []

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            if homeworks != last_homework:
                last_homework = homeworks
                message = parse_status(homeworks[0])
                send_message(bot, message)
            current_timestamp = response.get('current_date')
            last_message = None

        except NotForSendingError as error:
            logging.debug(f'Сбой в работе программы: {error}')

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.critical(message)
            if message != last_message:
                send_message(bot, message)
                last_message = message

        finally:
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
