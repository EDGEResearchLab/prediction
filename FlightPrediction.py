#Prediction

import sys, os, time, math
import urllib
import urllib2
import string
import xml.etree.ElementTree as ET
from NmeaReader import get_points

NMEAFILE = "./logs/out.log"
groundLevel = 1463 #m
payloadWeight = 12 #lbs
adaptiveWeightCorrection = 0 #+/- difference in lbs (actually compensates for wrong drag coefficients as well)

#parachuteDiagonal=


class PayloadStatus:
    """docstring for PayloadStatus"""
    def __init__(self, location, time, speed = 0, ascentRate = 0):
        self.location = location
        self.time = time
        self.speed = speed
        self.ascentRate = ascentRate

    def isFalling(self):
        if (self.ascentRate < -4):            ###Falling constant?
            return True
        return False

        
class Location:
    """docstring for Location"""
    def __init__(self, lat, lng, alt):
        #super(Location, self).__init__()
        self.latitude = lat
        self.longitude = lng
        self.altitude = alt

    def addDelta(self,lat,lng,alt):
        self.latitude += lat
        self.longitude += lng
        self.altitude += alt

        
#wind vectors by altitude
class Wind:
    """docstring for Wind"""
    def __init__(self, velocity, bearing, altitude):
        self.velocity = velocity
        self.bearing = bearing
        self.altitude = altitude

    def windAloft(self):                                            # Returns the wind values in form of wind aloft as described 
        waBearing = math.round(self.bearing/10)
        waVelocity = self.velocity
        if (waVelocity > 99):                                   # if the wind speed is +100 knots weird things happen as we only have 2 digits to represent
            waBearing += 50                                     # Wildy contrived + 50 to the 2 digit degrees
            waVelocity -= 100                                   
            if (waVelocity > 99):
                waVelocity=99                                   # yes the maximum represntable wind speed is 199 knots
        return (waBearing * 100 + waVelocity)

    def windAloftAltitude(self):
        return altitude

    def setByWindAloft(self,windAloftform,altitude=None):           #Sets the wind velocity, bearing, and alt. by wind aloft string
        windAloftform = str(windAloftform)[:4]                  # Make it a string and grab just the first 4 digits
        self.bearing = int(windAloftform[:2]) * 10
        self.velocity = int (windAloftform[2:4])
        if (self.bearing > 360):
            self.bearing -= 500
            self.velocity += 100
        self.altitude = altitude

    def setByLatLngTimeAtAlt(self, latStep, lngStep, timeStep, alt):        # k making crap fast - deltas lagStep lngStep timeStep in sec - at actual alt
        #1/60 of an arc = 1 knot
        # Please make this correct and not a guess  - though for empirical uses it will be fine
        x = (latStep/60.0) * 3600.0/timeStep
        y = (lngStep/60.0) * 3600.0/timeStep
        self.bearing = math.degrees(math.tan(y/x))
        self.velocity = math.sqrt(y*y + x*x)
        self.altitude = altitude
    
    def getLatVelocity(self):
        return math.sin(math.radians(self.bearing)) * self.velocity

    def getLngVelocity(self):
        return math.cos(math.radians(self.bearing)) * self.velocity

class WindString:
    """docstring for WindString"""
    winds = []
    """docstring for Wind"""
    def __init__(self):
        pass

    def appendWind(self, newWind):
        #print newWind.velocity
        if newWind.velocity > .007: # .0019:
            #print newWind.velocity
            newWind.velocity = 0
        if len(self.winds) == 0:
            self.winds.append(newWind)
        else:
            i = 0 
            while self.winds[i].altitude > newWind.altitude and i < len(self.winds):
                i += 1
            self.winds.insert(i,newWind)

    def getWindAtAlt(self, targetAltitude, t=0):
        if len(self.winds) > 1:
            for i in range(len(self.winds)):
                if self.winds[i].altitude < targetAltitude:
                    return interpolateWind(self.winds[i-1], self.winds[i], targetAltitude)
        return self.winds[-1]

def interpolateWind(lowWind, highWind, targetAltitude):         ## OH POOP I'm so bad at python where does this go or how should it be used?
    #this is where improvements will be made.  This currently only lineraly interpolates between the two vectors
    ratioOfHighToLow = (targetAltitude - lowWind.altitude) / (highWind.altitude - lowWind.altitude)
    latDelta = (lowWind.getLatVelocity() * (1 - ratioOfHighToLow) ) + (highWind.getLatVelocity() * ratioOfHighToLow)
    lngDelta = (lowWind.getLngVelocity() * (1 - ratioOfHighToLow) ) + (highWind.getLngVelocity() * ratioOfHighToLow)
    iVelocity = math.sqrt(latDelta*latDelta + lngDelta*lngDelta) # not what we are doing: highWind.velocity * ratioOfHighToLow + lowWind.velocity * (1 - ratioOfHighToLow)
    iBearing =  computeBearing(latDelta,lngDelta)
    return Wind(iVelocity, iBearing, targetAltitude)
    #return Wind(lowWind.velocity, lowWind.bearing, targetAltitude) # no crazy interpolation


class PayloadPath:
    """docstring for PayloadPath"""
    global adaptiveWeightCorrection
    global payloadWeight
    def __init__(self):
        #super(PayloadPath, self).__init__()
        #self.arg = arg
        self.path = []

    def predictDecsentPath(self, windField, currentStatus):
        #Predict Decsent path (lat/lng, alt at specific times)
        self.path.append(currentStatus)

        def my_range(start, end, step):
            while start > end:
                yield start
                start -= step
        #descent prediction only
        altDelta = 1.0 # we are really predicting 1m at a time - MEGA RESOLUTION!!!
        #groundLevel # NEED FUNCTION to get ground alt at guessed landing point
        for x in my_range(currentStatus.location.altitude, groundLevel, altDelta):  #lets try this range thing
            timeDelta = altDelta*self.descentTime(self.path[-1])
            latDelta = windField.getWindAtAlt(x).getLatVelocity() * (timeDelta)     #knots / sec
            lngDelta = windField.getWindAtAlt(x).getLngVelocity() * (timeDelta)     #knots / sec
            #print timeDelta
            #speed = getWindAtAlt(x).velocity                           #knots - not taking verticle speed into account - useless but kinda cool I guess 
            #append new +=lat/lng, alt, time, to path array
            nextLocation = Location(self.path[-1].location.latitude, self.path[-1].location.longitude, self.path[-1].location.altitude)
            nextLocation.addDelta(latDelta,lngDelta,((-1)*altDelta))
            nextTime = self.path[-1].time + timeDelta
            #print nextLocation.latitude, nextLocation.longitude, nextLocation.altitude, nextTime
            self.path.append(PayloadStatus(nextLocation,nextTime))

                ######nooo self.path[-1].latitude + latDelta, self.path[-1].longitude + lngDelta, self.path[-1].altitude + altDelta), self.path[-1].t + timeDelta))

        
    def predictBurst():         ## really not sure this is a function for this class - in fact, it really doesn't belong at all
        #Predict burst
        #spit out a guess in meters
        return 33000
    def ascentTime(self, payloadStatus):
        #Predict ascent rate - time traveling through each altitude zone
            #Adapt ascent rate
        return 0.5 #.01 sec/meter
    def descentTime(self, payloadStatus):
        #Predict decent rate
        #Adapt decent rate time traveling through each altitude zone
        x = payloadStatus.location.altitude
        #if x > 5000:
        #    return (math.log(x) * (-0.05688)) + .32334   #sec/meter .06 
        #return ((-0.0000004) * x) + 0.152 #sec/meter 0.132 #
        #return ((-0.0000004) * x) + 0.11464 #sec/meter 0.114 #
        #print adaptiveWeightCorrection
        # TODO use better atmosphere model
        return (1 / descentVelocity(x, payloadWeight + adaptiveWeightCorrection))

def aparentWeightCorrection(point1, point2):
    additionalWeight = 0
    if (point1.isFalling()):
        averageDescentRate = (((point2.ascentRate - point1.ascentRate) / 2.0) + point1.ascentRate) * -1.0
        averageAltitude = (((point2.location.altitude - point1.location.altitude) / 2.0) + point1.location.altitude)
        additionalWeight = (pow(averageDescentRate,2) * airDensityAtAlt(averageAltitude)) / combinedDragCoefficient(averageAltitude) - payloadWeight
        if additionalWeight > 25:
            print "WOAH THERE - You are falling way faster than expected! I'll back the estimated added weight to 10lbs down from" + str(additionalWeight)
            additionalWeight = 25
        if additionalWeight < -15:
            print "WOAH THERE - You are falling way slower than expected! I'll back the estimated added weight to 10lbs down from" + str(additionalWeight)
            additionalWeight = -15
    return additionalWeight

def combinedDragCoefficient(altitude):
    if (altitude > 17000):
        return 12.0 #chute not open drag ~=.? not much
    elif (altitude > 8000): #26.2ft
        return 4.0 #chute not open drag ~=.5
    else:
        return 2.996 #chute open drag =.75 at 4m^2 chute
    
def airDensityAtAlt(altitude):      #MAGIC
    altitude = altitude/1000
    density = 1.22 #kg/m3
    if (altitude<10000):
        density = (0.0000953350 * math.pow(altitude,2)) - (0.116 * altitude) + 1.23
    elif (altitude<20000):
        density = ( -0.0000953 * math.pow(altitude,3)) + (0.00669 * math.pow(altitude,2)) - (0.0167 * altitude) + 1.52
    else:
        density = ( -0.0000118 * math.pow(altitude,3)) + (0.00132 * math.pow(altitude,2)) - (0.0505 * altitude) + .0661
    return density

def descentVelocity(altitude,apparentWeight):
    #print airDensityAtAlt(altitude)
    #print altitude
    return math.sqrt((combinedDragCoefficient(altitude) * apparentWeight) / airDensityAtAlt(altitude))
    
def computeBearing(lat,lng):
    bearing = 0
    if lng == 0:
        if lat > 0:
            bearing = 90
        elif lng < 0:
            bearing = 270
    else:
        if lat == 0:
            if lng < 0:
                bearing == 180
        else:
            bearing = math.degrees(math.atan(lat/lng))
            if bearing < 0:
                bearing += 360
    return bearing

def measuredWindFromFlightPoints(point1, point2):
    timeStep = point2.time - point1.time
    #print timeStep
    latDelta = point2.location.latitude - point1.location.latitude
    lngDelta = point2.location.longitude - point1.location.longitude
    avgAltitude = (point2.location.altitude - point1.location.altitude)/2 + point1.location.altitude        #average altitude beteween data addMeasuredWindFromFlightPoint
    bearing = computeBearing(latDelta,lngDelta)
    velocity = math.sqrt(latDelta * latDelta + lngDelta * lngDelta) / timeStep
    #print velocity, bearing, avgAltitude, timeStep
    return Wind(velocity, bearing, avgAltitude)

#this belongs somewhere else
def findAscentRate(alt,time,oldPoint):
    timeStep = time - oldPoint.time
    ascentRate = (alt - oldPoint.location.altitude) / timeStep #in +/- m/s
    #print ascentRate
    return ascentRate
#this belongs somewhere else
#future self: please make this average the recent ascent rates within a reasonable timespan to get a more valid ascent rate
def findRecentAverageAscentRate(point1, point2):
    return (point1.ascentRate + point2.ascentRate)/2.0

def dd2dms(decDegrees):
    degrees = int(decDegrees)
    decMinutes = (decDegrees - degrees) * 60.0
    minutes = int(decMinutes) 
    decSeconds = (decMinutes - minutes) * 60.0
    seconds = int(decSeconds)
    tenths = (decSeconds - seconds) * 10
    return ({'Degrees':degrees, 'Minutes':minutes, 'Seconds':int(decSeconds*10000)/10000.0, 'Tenths':tenths})

def formatDMS(dms):
    return (str(dms['Degrees']) + "* " + str(dms['Minutes']) + "' " + str(dms['Seconds']) + '"')

def main():
    global adaptiveWeightCorrection
    global payloadWeight
    #edgeId = sys.argv[1]

    flightPoints = get_points(NMEAFILE)

    initialLocation = Location(5,5,5)
    windField = WindString()

    #populate windField
    windField.appendWind(Wind(0,0,0))
    #do some for loop stuff with some forcast

    #measure winds by flight path
    # read in flight data points at a time and  create a [] of lat lng, alt, times
    flight = []

    try:
        for i in range(0,len(flightPoints),10):
            dp = flightPoints[i]
            time = dp.time
            speed = 0#dp.speed
            lat = dp.latitude
            lng = dp.longitude
            alt = dp.altitude

            if len(flight) == 0:            #initialize that first one
                flight.append(PayloadStatus(Location(lat,lng,alt), time, speed, 0))
            if time != flight[-1].time:
                #print lat,lng,alt,speed,time
                flight.append(PayloadStatus(Location(lat,lng,alt), time, speed, findAscentRate(alt,time,flight[-1])))
                if len(flight) > 3:
                    windField.appendWind(measuredWindFromFlightPoints(flight[-2],flight[-1]))
                    #print len(windField.winds)
            else:
                flight.append(PayloadStatus(Location(lat,lng,alt), time, speed, flight[-1].ascentRate))
    
        #for w in windField.winds:
        #   print w.velocity, " knots at ", w.bearing, " degrees at", w.altitude, "meters"

        if len(flight) > 2:
            adaptiveWeightCorrection = aparentWeightCorrection(flight[-2],flight[-1]) # MAN MY NAMES ARE THE WORST
            print adaptiveWeightCorrection

        descentPrediction = PayloadPath()
        descentPrediction.predictDecsentPath(windField, flight[-1])
        
        landingPoint = {
            #'edgeId':edgeId,
            'longitude':descentPrediction.path[-1].location.longitude,
            'latitude':descentPrediction.path[-1].location.latitude
            }
        #sendPrediction(landingPoint);
        print landingPoint
        print {'longitude':formatDMS(dd2dms(landingPoint['longitude'])), 'latitude':formatDMS(dd2dms(landingPoint['latitude']))}

    except IOError as e: # Usually just means that the xml isn't online yet.
        return

if __name__ == '__main__':
    main()
