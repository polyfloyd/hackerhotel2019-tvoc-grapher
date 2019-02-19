from machine import I2C, Pin
import math
import time
import ugfx

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
            'co2_ppm':  resp[0]<<8 | resp[1],
            'tvoc_ppb': resp[2]<<8 | resp[3],
        }

    def _measure_raw_signals(self):
        return self._cmd(0x2050, 2)

    """
    Performs a test intended for use in a post manufacturing self test.
    """
    def measure_test(self):
        if self._init:
            raise Exception('Can not self test after initial reading')
        # A unique # serial ID with a length of 48bits.
        resp = self._cmd(0x2032, 1, wait=0.25)
        assert resp == b'\xd4\x00'

    """
    Measures the air quality and returns it as a dict with two entries:
      * 'tvoc_ppb': An int of the Total Volatile Organic Compound count in
                    parts per billion.
      * 'co2_ppm': An int of the equivalent CO2 count in parts per million.

    Because the chip needs to perform a callibration, the first 10 to 20
    readings return 0 PPB TVOC and 400 ppm eCO2. For both readings, the
    measurement clips at 60000.

    The chip has a has a dynamic baseline compensation algorithm that works
    best when this function is called in intervals of 1 second.
    """
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


BADGE_EINK_WIDTH  = 296
BADGE_EINK_HEIGHT = 128

ugfx.init()

i2c = I2C(sda=Pin(26), scl=Pin(27), freq=100000)
sgp30 = SGP30(i2c)
history = [(0, 0)] * BADGE_EINK_WIDTH


while True:
    measurement = sgp30.air_quality()
    print(measurement)
    co2_ppm = measurement['co2_ppm']
    tvoc_ppb = measurement['tvoc_ppb']

    log_max = math.log(60000)
    co2_y = int(math.log(max(co2_ppm, 1)) / log_max * 64)
    tvoc_y = int(math.log(max(tvoc_ppb, 1)) / log_max * 64)
    _ = history.pop(0)
    history.append((co2_y, tvoc_y))

    ugfx.clear(ugfx.WHITE)
    ugfx.line(0, 64, BADGE_EINK_WIDTH, 64, ugfx.BLACK)
    ugfx.string(0, 0, 'eCO2: %d ppm' % co2_ppm, 'Roboto_Regular18', ugfx.BLACK)
    ugfx.string(0, 64, 'TVOC: %d ppb' % tvoc_ppb, 'Roboto_Regular18', ugfx.BLACK)

    for (x, (a, b)) in enumerate(zip(history, history[1:])):
        ugfx.thickline(x, 64 - a[0], x+1, 64 - b[0], ugfx.BLACK, 2, 0)
        ugfx.thickline(x, (64 - a[1]) + 64, x+1, (64 - b[1]) + 64, ugfx.BLACK, 2, 0)

    ugfx.flush()

    time.sleep(1)
