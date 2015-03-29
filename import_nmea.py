#!/usr/bin/env python2

from __future__ import print_function


class _Parsable(object):
    def __init__(self, string):
        if not string is None:
            self.parse(string)

    def parse(self, string):
        raise NotImplementedError('Not implemented.')

    def __getitem__(self, key):
        return self.__dict__[key]

    def __repr__(self):
        string = '{'
        for k, v in self.__dict__.items():
            string += '{k}={v};'.format(k=k, v=v)
        string += '}'
        return string

    def __str__(self):
        return self.__repr__()


class PEDGE(_Parsable):
    def __init__(self, sentence=None):
        self.id = None
        self.balloon_id = None
        self.date = None
        self.time = None
        self.latitude = None # dd
        self.longitude = None # dd
        self.altitude = None # meters
        self.speed = None
        self.course = None
        self.numsats = None
        self.hdop = None

        super(PEDGE, self).__init__(sentence)

    def parse(self, string):
        vals = string.split(',')
        self.id = vals[0]
        self.balloon_id = vals[1]
        self.date = vals[2]
        self.time = int(vals[3])
        self.latitude = float(vals[4])
        self.longitude = float(vals[5])
        self.altitude = int(float(vals[6]))
        self.speed = float(vals[7])
        self.course = vals[8]
        self.numsats = int(vals[9])
        self.hdop = vals[10]


class GPGGA(_Parsable):
    class FIX_QUALITY:
        INVALID = 0
        GPS = 1
        DGPS = 2
        PPS = 3
        KINEMATIC = 4
        RTK = 5
        ESTIMATED = 6
        MANUAL = 7
        SIMULATION = 8

        @classmethod
        def from_int(cls, val):
            for k, v in cls.__dict__.items():
                if v == val:
                    return cls.__dict__[k]
            raise ValueError('Invalid Fix Value.')

    def __init__(self, sentence=None):
        self.id = None
        self.time = None
        self.latitude = None
        self.longitude = None
        self.fix = None
        self.sats = None
        self.dilution = None
        self.altitude = None
        self.geoid = None

        super(GPGGA, self).__init__(sentence)

    def parse(self, string):
        vals = string.split(',')
        self.id = vals[0]
        self.time = int(self._time_to_seconds_in_day(vals[1]))
        self.latitude = float(self._dir_to_sign(vals[3]) * self._ddm_to_dd(vals[2]))
        self.longitude = float(self._dir_to_sign(vals[5]) * self._ddm_to_dd(vals[4]))
        self.fix = self.FIX_QUALITY.from_int(int(vals[6]))
        self.sats = int(vals[7])
        self.dilution = float(vals[8])
        self.altitude = float(vals[9])
        self.geoid = float(vals[11])

    def _ddm_to_dd(self, val):
        """Convert degree decimal minutes to decimal degrees"""
        # we get this as DDDMM.NNN
        print("VALUE: ", val)
        degs = int(float(val) / 100)
        # drop the degrees off the front
        mins = ((float(val) / 100) - degs) * 100
        return degs + (mins / 60)

    def _dir_to_sign(self, direction):
        if direction.upper() in ['N', 'E']:
            return 1
        else:
            return -1

    def _time_to_seconds_in_day(self, timeval):
        timeval = int(float(timeval))
        secs = timeval % 100
        mins = (timeval / 100) % 100
        hours = timeval / 10000
        return (hours * 3600) + (mins * 60) + secs


class NMEA:
    _sentence_parsers = {
        '$GPGGA': GPGGA,
        '$PEDGE': PEDGE
    }

    @classmethod
    def register_parser(cls, sentence_id, parsable):
        cls._sentence_parsers[str(sentence_id)] = parsable

    @classmethod
    def parse(cls, sentence, validate=True):
        if validate and not cls.is_valid_sentence(sentence):
            raise cls.InvalidSentence('Bad NMEA Sentence.')

        if sentence[:6] not in cls._sentence_parsers:
            raise cls.InvalidSentence('Unable to parse sentence type "{}"'.format(sentence[:6]))

        return cls._sentence_parsers[sentence[:6]](sentence)

    @staticmethod
    def is_valid_sentence(sentence):
        if not isinstance(sentence, str):
            raise ValueError('Sentence not a string type.')

        sentence = sentence.strip()
        if sentence[0] != '$' or sentence[-3] != '*':
            return False

        chk = 0x00
        for c in sentence[1:-3]:
            chk ^= ord(c)
        return hex(chk) == '0x' + sentence[-2:].lower()

    class InvalidSentence(Exception):
        pass


def get_points(nmeafile, sentence_id_filter='$GPGGA'):
    nmea_points = []
    with open(nmeafile, 'r') as f:
        for line in f.readlines():
            try:
                if sentence_id_filter in line:
                    nmea_points.append(NMEA.parse(line.strip()))
            except Exception as e:
                print('Parser error:', e)
    return nmea_points


if __name__ == '__main__':
    print(get_points('./logs/out.log', '$PEDGE'))
