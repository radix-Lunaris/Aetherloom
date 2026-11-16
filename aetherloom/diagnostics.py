"""Detailed, bounded client event log. Never accept request bodies or tokens."""
import logging
from logging.handlers import TimedRotatingFileHandler
import re

logger = logging.getLogger('aetherloom.client')
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.NullHandler())

def setup(directory):
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handler = TimedRotatingFileHandler(directory/'client.log', when='midnight', backupCount=5, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        for old in list(logger.handlers):
            logger.removeHandler(old);old.close()
        logger.addHandler(handler)
    except OSError: pass

def safe(message):
    return re.sub(r'(?i)(bearer\s+|(?:token|password|resume|punch_key|secret)[\s\"\x27]*[:=][\s\"\x27]*)([^\s,}\"\x27]+)', r'\1[REDACTED]', str(message))

def event(code, **fields):
    logger.debug('EVENT code=%s %s', code, ' '.join(f'{k}={safe(v)!r}' for k,v in fields.items()))

def close():
    for handler in list(logger.handlers):
        logger.removeHandler(handler);handler.close()
