import ipaddress
from _socket import gethostbyname

import pyVoIP


__all__ = [
            'Connection'
          ]


debug = pyVoIP.debug


class Connection:

    def __init__(self, address: str, port=5060):
        self.ip = None
        self.uri = None
        self.ip_type = None
        self.port = port
        self.set_values(address)

    def set_values(self, address: str) -> None:
        is_ip = self.check_ip_and_type(address)
        if not is_ip:
            self.uri = address

    def get_address(self):
        if self.ip is not None:
            return self.ip
        if self.uri is not None:
            return self.uri
        return None

    def get_port(self) -> int:
        return self.port

    def check_ip_and_type(self, address) -> bool:
        try:
            debug('DEBUG', f"{address} as ip {gethostbyname(address)}")
            ip = ipaddress.ip_address(gethostbyname(address))
            self.ip = address
            if isinstance(ip, ipaddress.IPv4Address):
                self.ip_type = 'IPv4'
                debug('DEBUG', f"{address} is an IPv4 address")
                return True
            elif isinstance(ip, ipaddress.IPv6Address):
                self.ip_type = 'IPv6'
                debug('DEBUG', f"{address} is an IPv6 address")
                return True
        except ValueError:
            debug('DEBUG', f"{address} is an invalid IP address")
            return False

    def summary(self):
        print(f'IP: {self.ip}, IP type: {self.ip_type} URI: {self.uri}, port: {self.port}')


if __name__ == '__main__':
    connection = Connection('192.168.188.20', 5060)
    connection.summary()
    print(f'get_address {connection.get_address()}')

    connection = Connection('sip2sip.info', 5061)
    connection.summary()
    print(f'get_address {connection.get_address()}')

