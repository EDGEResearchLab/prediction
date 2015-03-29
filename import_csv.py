from collections import namedtuple

class flightPoints(object):
    """docstring for flightPoints"""
    def __init__(self):
        super(flightPoints, self).__init__()
        self.time = None
        self.latitude = None # dd
        self.longitude = None # dd
        self.altitude = None # meters
    def __getitem__(self, key):
        return self.__dict__[key]

def get_csv_points(csvfile):
    csv_points = []
    with open(csvfile, 'r') as f:
        for line in f.readlines():
            try:
                point_list = line.strip().split(',')
                point_obj = flightPoints()
                point_obj.latitude = float(point_list[1])
                point_obj.longitude = float(point_list[2])
                point_obj.altitude = float(point_list[3])
                point_obj.time = int(point_list[4])
                csv_points.append(point_obj)
            except Exception as e:
                print('Parser error:', e)
    return csv_points
