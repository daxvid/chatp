import datetime

__all__ = ['SIP', 'RTP', 'VoIP']

version_info = (1, 6, 3)

__version__ = ".".join([str(x) for x in version_info])

DEBUG = 'DEBUG'

TRANSMIT_DELAY_REDUCTION = 0.0

# ALL < DEBUG < INFO < WARN < ERROR < FATAL < OFF.
DEBUG_LEVEL = ['OFF', 'FATAL', 'ERROR', 'WARN', 'INFO', 'DEBUG', 'ALL']


def debug(level, s, e=None):
    if DEBUG_LEVEL.index(level) <= DEBUG_LEVEL.index(DEBUG):
        print(f'{datetime.datetime.now().strftime("%d.%b %Y %H:%M:%S")} [{level}] - {s}')
    elif e is not None:
        print(f'{datetime.datetime.now().strftime("%d.%b %Y %H:%M:%S")} [{level}] - {e}')


# noqa because import will fail if debug is not defined
from pyVoIP.RTP import PayloadType  # noqa: E402

SIPCompatibleMethods = ['INVITE', 'ACK', 'BYE', 'CANCEL', 'NOTIFY']

SIPCompatibleVersions = ['SIP/2.0']

RTPCompatibleVersions = [2]
RTPCompatibleCodecs = [PayloadType.PCMU, PayloadType.PCMA, PayloadType.EVENT]
