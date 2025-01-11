from notifiers import get_notifier
from notifiers.exceptions import BadArguments
from os import environ
from xmpp import *
import requests

telegram = get_notifier('telegram')

def telegram_notify(message, title: str = None):
    try:
        if title:
            message = f"<b>{title}</b>\n{message}"

        r = telegram.notify(message=message,
                            parse_mode='html')
    except BadArguments as e:
        print(f'Telegram notifications require NOTIFIERS_TELEGRAM_CHAT_ID'
              f' and NOTIFIERS_TELEGRAM_TOKEN environments to be exported. Detailed exception:\n{e}')
        return

    if r.status != 'Success':
        print(f'Telegram notification failed\n{r.errors}')
