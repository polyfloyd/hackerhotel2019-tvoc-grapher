import time
from machine import I2C, Pin

# https://www.mouser.com/ds/2/682/Sensirion_Gas_Sensors_SGP30_Datasheet_EN-1148053.pdf
class SGP30:
    ADDR = 0x58

    def __init__(self, i2c):
        devices = i2c.scan()
        if SGP30.ADDR not in devices:
            raise Exception('SGP30 not found on I2C bus')
        self._i2c = i2c
        self._init = False
        self._get_serial_id()

    def _cmd(self, opcode, response_words, wait=0.01):
        self._i2c.writeto(SGP30.ADDR, bytes([opcode >> 8, opcode & 0xff]))
        time.sleep(wait)

        if response_words == 0:
            return b''
        resp = self._i2c.readfrom(SGP30.ADDR, response_words * 3)

        resp_bytes = bytearray()
        for i in range(0, response_words):
            word = resp[i*3:i*3+2]
            if SGP30._crc8(word) != resp[i*3+2]:
                raise Exception('CRC verification failure')
            resp_bytes += word
        return resp_bytes

    def _get_serial_id(self):
        # A unique # serial ID with a length of 48bits.
        return self._cmd(0x3682, 3)

    def _init_air_quality(self):
        return self._cmd(0x2003, 0)

    def _measure_air_quality(self):
        # The sensor responds with 2 data bytes (MSB first) and 1 CRC byte for
        # each of the two preprocessed air quality signals in the order CO2eq
        # (ppm) and TVOC(ppb)
        resp = self._cmd(0x2008, 2)
        return {
            'co2_ppm': resp[0]<<8 | resp[1],
            'tvoc_ppb': resp[2]<<8 | resp[3],
        }

    def _measure_raw_signals(self):
        return self._cmd(0x2050, 2)

    def measure_test(self):
        if self._init:
            raise Exception('Can not self test after initial reading')
        # A unique # serial ID with a length of 48bits.
        resp = self._cmd(0x2032, 1, wait=0.25)
        assert resp == b'\xd4\x00'

    def air_quality(self):
        if not self._init:
            self._init_air_quality()
            self._init = True
        return self._measure_air_quality()

    @staticmethod
    def _crc8(data):
        poly = 0x31
        crc = 0xff
        for b in data:
            crc ^= b
            for j in range(0, 8):
                crc = ((crc<<1)^poly)&0xff if crc & 0x80 else crc<<1
        return crc


i2c = I2C(sda=Pin(26), scl=Pin(27), freq=100000)
sgp30 = SGP30(i2c)
print('SGP30 found')

while True:
    print(sgp30.air_quality())
    time.sleep(1)
