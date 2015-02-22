#Prediction

import sys, os, time, math
import urllib
import urllib2
import string
import xml.etree.ElementTree as ET
#from NmeaReader import get_points
from import_csv import get_csv_points


class PayloadStatus:
    """docstring for PayloadStatus"""
    def __init__(self, location, time, speed = 0, ascentRate = 0, actualWeight = 1):
        self.location = location
        self.time = time
        self.speed = speed
        self.ascentRate = ascentRate
        self.actualWeight = actualWeight;
        self.apparentWeight = self.actualWeight;

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

def interpolateWind(lowWind, highWind, targetAltitude):
    #this is where improvements will be made.  This currently only lineraly interpolates between the two vectors
    ratioOfHighToLow = (targetAltitude - lowWind.altitude) / (highWind.altitude - lowWind.altitude)
    latDelta = (lowWind.getLatVelocity() * (1 - ratioOfHighToLow) ) + (highWind.getLatVelocity() * ratioOfHighToLow)
    lngDelta = (lowWind.getLngVelocity() * (1 - ratioOfHighToLow) ) + (highWind.getLngVelocity() * ratioOfHighToLow)
    iVelocity = math.sqrt(latDelta*latDelta + lngDelta*lngDelta) # not what we are doing: highWind.velocity * ratioOfHighToLow + lowWind.velocity * (1 - ratioOfHighToLow)
    iBearing =  computeBearing(latDelta,lngDelta)
    return Wind(iVelocity, iBearing, targetAltitude)
    #return Wind(lowWind.velocity, lowWind.bearing, targetAltitude) # no interpolation


class PayloadPath:
    """docstring for PayloadPath"""
    global adaptiveWeightCorrection
    global payloadWeight
    def __init__(self):
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
        groundLevel = 1595 #m # NEED FUNCTION to get ground alt at guessed landing point
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
            self.path.append(PayloadStatus(nextLocation,nextTime,0,0,self.path[-1].apparentWeight))

    def descentTime(self, payloadStatus):
        #Predict decent rate
        #Adapt decent rate time traveling through each altitude zone
        x = payloadStatus.location.altitude
        return (1 / descentVelocity(x, payloadStatus.apparentWeight))

def apparentWeightCorrection(point1, point2):
    additionalWeight = 0
    if (point1.isFalling()):
        averageDescentRate = (((point2.ascentRate - point1.ascentRate) / 2.0) + point1.ascentRate) * -1.0
        averageAltitude = (((point2.location.altitude - point1.location.altitude) / 2.0) + point1.location.altitude)
        additionalWeight = (pow(averageDescentRate,2) * airDensityAtAlt(averageAltitude)) / combinedDragCoefficient(averageAltitude) - point1.actualWeight
        if additionalWeight > 20:
            print "WOAH THERE - You are falling way faster than expected! I'll back the estimated added weight to 20lbs down from" + str(additionalWeight)
            additionalWeight = 20
        if additionalWeight < -20:
            print "WOAH THERE - You are falling way slower than expected! I'll back the estimated added weight to -20lbs down from" + str(additionalWeight)
            additionalWeight = -20
    return additionalWeight

def combinedDragCoefficient(altitude):
    if (altitude > 17000):
        return 12.0 #chute not open drag ~=.? not much
    elif (altitude > 8000): #26.2ft
        return 4.0 #chute not open drag ~=.5
    else:
        return 2.996 #chute open drag =.75 at 4m^2 chute
    
def airDensityAtAlt(altitude):      #MAGIC based off NASA's standard day
    #init to sea level for reference
    density = 1.22 #kg/m3
    kPa = 101 #kPa
    airTemp = 15.0 #C
    if (altitude<11000):
        airTemp = 15.04 - 0.00649 * altitude
        kPa = 101.29 * math.pow(((airTemp + 273.1)/288.08),5.256)
    elif (altitude<25000):
        airTemp = -56.46
        kPa = 22.65 * math.exp(1.73 - 0.000157 * altitude)
    else:
        airTemp = -131.21 + 0.00299 * altitude
        kPa = 2.488 * math.pow(((airTemp + 273.1)/ 216.6),-11.388)
    density = kPa / (0.2869 * (airTemp + 273.1))
    return density

def descentVelocity(altitude,apparentWeight):
    #print airDensityAtAlt(altitude)
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
    payloadWeight = 11

    #flightPoints = get_nmea_points(POINTSFILES)
    flightPoints = get_csv_points(sys.argv[1])

    initialLocation = Location(5,5,5)
    windField = WindString()

    #populate windField
    windField.appendWind(Wind(0,0,0))
    #do some for loop stuff with some forcast

    #measure winds by flight path
    # read in flight data points at a time and  create a [] of lat lng, alt, times
    flight = []

    try:
        for i in range(0,len(flightPoints),1):
            dp = flightPoints[i]
            time = dp.time
            speed = 0#dp.speed
            lat = dp.latitude
            lng = dp.longitude
            alt = dp.altitude

            if len(flight) == 0:            #initialize that first one
                flight.append(PayloadStatus(Location(lat,lng,alt), time, speed, 0, payloadWeight))
            if time != flight[-1].time:
                #print lat,lng,alt,speed,time
                flight.append(PayloadStatus(Location(lat,lng,alt), time, speed, findAscentRate(alt,time,flight[-1]), payloadWeight))
                if len(flight) > 3:
                    windField.appendWind(measuredWindFromFlightPoints(flight[-2],flight[-1]))
                    print flight[-1].time - flight[-2].time
                    #print len(windField.winds)
            #else:  #What was I thinking?
            #    flight.append(PayloadStatus(Location(lat,lng,alt), time, speed, flight[-1].ascentRate))
    
        for w in windField.winds:
           print w.velocity * 100000, " knots at ", w.bearing, " degrees at", w.altitude, "meters"

        if len(flight) > 2:
            adaptiveWeightCorrection = apparentWeightCorrection(flight[-2],flight[-1])
            print adaptiveWeightCorrection
            flight[-1].apparentWeight = flight[-1].actualWeight + adaptiveWeightCorrection


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
