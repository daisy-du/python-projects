import requests
import json
import pandas as pd
import geopy.distance
from datetime import timedelta 
import gpxpy
import gpxpy.gpx
import base64
import statistics 
import math
import datetime
import argparse

# get user inputs through command-line parsing
parser = argparse.ArgumentParser()

# Required arguments
parser.add_argument("start_date", type = str, help = "set the start date of the job")
parser.add_argument("end_date", type = str, help = "set the end date of the job")
parser.add_argument("network", type = str, help = "set the network of the job")
parser.add_argument("network_token", type = str, help = "set the network_token of the job")

# Optional arguments
parser.add_argument("verbosity", type = str, help = "set the verbosity of the job (v, vv, vvv)")
parser.add_argument("directory", type = str, help = "set the directory of the job")

# Get all values of the arguments
args = parser.parse_args()

# Assign global variables user input values 
start_date = args.start_date
end_date = args.end_date
network = args.network
network_api_token = args.network_token
verbosity_level = args.verbosity
directory = args.directory

if verbosity_level == 'vvv':
    print("Input Date Range: " + start_date + " to " + end_date)
    print("Input network: " + network)
    
print("Job started running ...")
    
# global variables    
headers = {'Authorization': "Token " + network_api_token}
here_api_key = '2f5REEm8jfkudjOIFQTB3Dwj8_KYuE5RO69HqvbLV64'

# Gets All Vehicles in the Network and Returns the first JSON Content
def fetchAssetPointList(): 
    
    # Fetch Data from Provided API Network
    base_url = "https://" + network + ".tv.recondynamics.com/api/v1/"

    # Get all the vehicles to get all the corresponding asset id 
    url_v = base_url + "asset-location?asset_type_category=Vehicle"
    response = requests.get(url = url_v, headers = headers)
    
    if verbosity_level == 'vvv' or verbosity_level == 'vv':
        print("Asset Location Request Status: " + str(response))
    
    vehicle_list = json.loads(response.content.decode('utf-8'))

    # Extract asset id for the endpoint, asset.asset_id for Vehicle ID, asset_type for Vehicel Type, and assigned location
    vehicle_ids = []
    vehicle_IDs = []
    vehicle_types = []
    vehicle_assigned_loc = []
    vehicle_names = []

    for vehicle in vehicle_list:
        vehicle_ids.append(vehicle['asset']['id'])
        vehicle_IDs.append(vehicle['asset']['asset_id'])
        vehicle_names.append(vehicle['asset']['name'])
        vehicle_types.append(vehicle['asset']['asset_type'])
        vehicle_assigned_loc.append(vehicle['assigned_location']['name'])

    asset_ids_param = str(vehicle_ids)[1:-1].replace(" ", "")
    # Example: &ordering=-timestamp&timestamp__gte=2020-07-20T00:00:00&timestamp__lte=2020-07-29T00:00:00
    date_param = "&ordering=-timestamp&timestamp__gte=" + start_date + "&timestamp__lte=" + end_date

    # Pass in assets ids in the endpoints to get all vehicles's points during the given time period
    url_p = base_url + "asset-point/?asset=" + asset_ids_param + date_param
    response = requests.get(url = url_p, headers = headers)
    
    if verbosity_level == 'vvv' or verbosity_level == 'vv':
        print("Asset Point Request Status: " + str(response))
        
    asset_points_list = json.loads(response.content.decode('utf-8'))
    
    vehicle_df = pd.DataFrame(list(zip(vehicle_ids, vehicle_IDs, vehicle_names, vehicle_types, vehicle_assigned_loc)),
                          columns = ['asset_id', 'Vehicle', 'Vehicle Name','Vehicle Type', 'Assigned Location'])
    
    return asset_points_list, vehicle_df 


# Given asset_points JSON Content, Returns All Asset Points in a pandas DataFrame
def fetchAssetPoints(asset_points_list):
    all_points = asset_points_list['results']
    while asset_points_list['next'] != None:
        curr_url = asset_points_list['next']
        response = requests.get(url = curr_url, headers = headers)
        curr_list = json.loads(response.content.decode('utf-8'))
        all_points += curr_list['results']
        asset_points_list['next'] = curr_list['next']

    # list to df to handle data
    asset_points_df = pd.DataFrame.from_records(all_points)
    return asset_points_df

# Given Meters, Return Miles
def getMiles(i):
    return i * 0.000621371192;

# Prep the Points Data to Generate Trips 
def processPoints(asset_points_df):
    asset_points_df["timestamp"] = pd.to_datetime(asset_points_df["timestamp"], format = "%Y-%m-%dT%H:%M:%SZ")
    asset_points_df = asset_points_df.sort_values(by = ['asset', 'timestamp'])
    asset_points_df['speed'] = asset_points_df['speed'].astype(float)
    asset_points_df.dropna(inplace = True)
    return asset_points_df

# Given Asset Points df, Mark and Return Stopping Points and Potential Trips Along the Way
def markTrips(asset_points_df):

    # Loop through each asset to get trips and stops for that asset 
    trips = []

    for asset_id in asset_points_df['asset'].unique():

        curr = asset_points_df[asset_points_df['asset'] == asset_id].sort_values(by=['timestamp'])
        pts = curr.values.tolist()

        prev_pt = None
        trip_id = 1
        distance_0_start = None
        distance_0_end = None

        for pt in pts:
            if prev_pt:
                asset_id = pt[1]
                distance = geopy.distance.distance((prev_pt[2]['lat'], prev_pt[2]['lng']),
                                                   (pt[2]['lat'], pt[2]['lng'])).meters
                delta_time =  pt[3] - prev_pt[3]

                if delta_time > timedelta(hours = 1):
                    trip_id = trip_id + 1
                    distance_0_start = None
                    distance_0_end = None
                else: 
                    start_time = prev_pt[3]
                    end_time = pt[3]
                    start_lat = prev_pt[2]['lat']
                    start_lon = prev_pt[2]['lng']
                    end_lat = pt[2]['lat']
                    end_lon = pt[2]['lng']

                    # If the stop lasts longer than 10 mins, mark as a new trip, 
                    # stop means moving less than 100 meters
                    # If the time delta is larger than 1 hour, mark as a new trip
                    if distance_0_start and distance_0_end:
                        if (distance_0_end - distance_0_start) > timedelta(minutes = 10):
                            trip_id = trip_id + 1

                    # When distance <= 100 meters, update start_time and end_time for the stop
                    if distance <= 100:
                        if not distance_0_start:
                            distance_0_start = start_time
                        distance_0_end = end_time
                    else:
                        # When distance is less then 100 meters, clear the distance_0_time recorder
                        distance_0_start = None
                        distance_0_end = None

                    trips.append({'start_time': start_time, 'end_time': end_time, 
                                  'distance': getMiles(distance), 'start_lat': start_lat, 
                                  'start_lon': start_lon, 'end_lat': end_lat, 
                                  'end_lon': end_lon, 'trip_id': trip_id, 
                                  'asset_id': asset_id})
            prev_pt = pt
            
    trips = pd.DataFrame.from_records(trips)
    return trips


# Given Stopping Points & Potential Trips, Return Real Trips
def getRealTrips(trips):
    prev_trip_id = None
    start_time = None
    end_time = None 
    start_point = None
    end_point = None
    point = ''
    new_trips = []
    asset_id = None

    for index, row in trips.iterrows():
        if not prev_trip_id and not start_time and not end_time and not start_point and not end_point: 
            start_time = row['start_time']
            end_time = row['end_time']
            prev_trip_id = row['trip_id']
            point = str(row['start_lat']) + " " + str(row['start_lon'])
            asset_id = row['asset_id']
        else: 
            if prev_trip_id == row['trip_id']:
                end_time = row['end_time']
                point = point +',' + str(row['start_lat']) + " " + str(row['start_lon'])
            else: 
                point = point +',' + str(row['start_lat']) + " " + str(row['start_lon'])
                # Add a new clean trip here 
                new_trips.append({'start_time': start_time, 'end_time': end_time, 'points': point, 'trip_id': prev_trip_id, 'asset_id': asset_id})

                # Update records once previous trip has been added
                prev_trip_id = row['trip_id']
                point = str(row['start_lat']) + " " + str(row['start_lon'])
                start_time = row['start_time']
                end_time = row['end_time']
                asset_id = row['asset_id']


    # Append One Last Trip 
    point = point +',' + str(row['end_lat']) + " " + str(row['end_lon'])
    new_trips.append({'start_time': start_time, 'end_time': end_time, 'points': point, 'trip_id': prev_trip_id, 'asset_id': asset_id})   
    
    # Filter out stopping points in the trips
    new_trips_df = pd.DataFrame.from_records(new_trips)
    new_trips_df = new_trips_df[new_trips_df.apply(lambda x: x['points'].split(",")[0] != x['points'].split(",")[1], axis=1)]
    new_trips = new_trips_df.values.tolist()
    
    return new_trips
    
    
def getDistanceAndEvents(new_trips, asset_points_df):
    distance_col = []
    speed_limits = []
    tracepoints = []

    for trip in new_trips:

        # For one trip
        # Creating a new file:
        # --------------------
        gpx = gpxpy.gpx.GPX()

        # Create first track in our GPX:
        gpx_track = gpxpy.gpx.GPXTrack()
        gpx.tracks.append(gpx_track)

        # Create first segment in our GPX track:
        gpx_segment = gpxpy.gpx.GPXTrackSegment()
        gpx_track.segments.append(gpx_segment)

        # Get the speed and pass in the gpx segment too
        start = trip[0]
        end = trip[1]
        asset_id = trip[4]
        speeds = asset_points_df.loc[(asset_points_df['asset'] == asset_id) & 
                        (asset_points_df['timestamp'] >= start) & 
                        (asset_points_df['timestamp'] <= end),['speed']]['speed']

        timestamps = asset_points_df.loc[(asset_points_df['asset'] == asset_id) & 
                        (asset_points_df['timestamp'] >= start) & 
                        (asset_points_df['timestamp'] <= end),['timestamp']]['timestamp']

        speeds = speeds.reset_index(drop = True)
        timestamps = timestamps.reset_index(drop = True)

        speed_index = 0
        time_index = 0

        for point in trip[2].split(","):
            lat = point.split(" ")[0]
            lng = point.split(" ")[1]
            if math.isnan(speeds[speed_index]):
                speeds[speed_index] = 0
            gpx_segment.points.append(gpxpy.gpx.GPXTrackPoint(float(lat), float(lng), 
                                                              speed = speeds[speed_index], 
                                                              time = pd.to_datetime(timestamps[time_index])))
            #print(speeds[speed_index])
            speed_index = speed_index + 1
            time_index = time_index + 1

        with open("output.gpx", "w") as f:
            f.write(gpx.to_xml(version="1.0"))

        with open("output.gpx", 'r') as f:
            file = f.read()

        url = "https://m.fleet.ls.hereapi.com/2/matchroute.json?apiKey=" + here_api_key + "&routemode=car&attributes=SPEED_LIMITS_FCn(FROM_REF_SPEED_LIMIT,TO_REF_SPEED_LIMIT)"
        # Get the distance data from HERE through the endpoints 
        # POST request has no limit for file size
        response = requests.post(url, data = file)
        trip_info_list = json.loads(response.content.decode('utf-8'))
        
        for tracepoint in trip_info_list['TracePoints']:
            # tracepoint is a dictionary
            tracepoint["asset_id"] = asset_id
            tracepoints.append(tracepoint)
        
        distance = 0
        # each trip has multiple routelinks which have multiple speed limits, we keep unique speed limits only
        
        for link in trip_info_list['RouteLinks']:
            distance = distance + link['linkLength']
            
            #print(distance)
            
            if len(link) == 7: 
                if link['linkId'] > 0:
                    speed_limit = round(int(link['attributes']['SPEED_LIMITS_FCN'][0]['FROM_REF_SPEED_LIMIT']) * 0.6214)
                else:
                    speed_limit = round(int(link['attributes']['SPEED_LIMITS_FCN'][0]['TO_REF_SPEED_LIMIT']) * 0.6214)
                
                speed_limits.append({'linkId': link['linkId'], 'speed_limit': speed_limit, 
                                     "asset_id": asset_id, 'trip_start': start, 'trip_end': end, 'shape': link['shape']})

        distance_col.append(getMiles(distance))
        
    # Converts lists to dataframes
    speed_limits = pd.DataFrame.from_records(speed_limits)
    tracepoints = pd.DataFrame.from_records(tracepoints)
    return distance_col, speed_limits, tracepoints

def convertTime(time):
    s = time / 1000.0
    hours_added = datetime.timedelta(hours = 7)
    d = datetime.datetime.fromtimestamp(s) + hours_added
    return pd.to_datetime(d)

def getTripsCSV(distance_col, real_trips, vehicle_df):
    df = pd.DataFrame.from_records(real_trips)
    df['distance'] = distance_col
    df = df[df['distance'] > 1]
    df = df.rename(columns = {0: "Trip Start", 1: "Trip End", 3: "trip_id", 4: "asset_id", "distance": "Distance"})
    df = df.drop(columns = [2, 'trip_id'])
    df = df.merge(vehicle_df, on = 'asset_id', how = 'left')
    df['delta_time'] = df.apply(lambda row: round((row['Trip End'] - row['Trip Start']).total_seconds() / 60), axis = 1)
    df.to_csv(directory + 'trip-9-16.csv')
    print("Finished generating trip.csv")
    return df

def getEventsCSV(speed_limits, tracepoints, vehicle_df):
    tracepoints = tracepoints.rename(columns = {'linkIdMatched': "linkId"})
    tracepoints = tracepoints[['lat', 'latMatched', 'linkId', 'lon', 'lonMatched', 'speedMps', 'timestamp', 'asset_id']]
    tracepoints['timestamp'] = tracepoints['timestamp'].apply(convertTime)
    
    merged = speed_limits.merge(tracepoints, on = ['linkId', 'asset_id'], how = 'left')
    merged.dropna(inplace = True)
    merged = merged[(merged['speed_limit'] < merged['speedMps'])]
    merged = merged[(merged['timestamp'] >= merged['trip_start']) & 
                    (merged['timestamp'] <= merged['trip_end'])]
    
    merged = merged.merge(vehicle_df, on = 'asset_id', how = 'left')
    merged = merged[['speed_limit', 'trip_start', 'trip_end', 'latMatched', 'lonMatched', 
                     'speedMps', 'timestamp', 'Vehicle', 'Vehicle Name', 'Vehicle Type', 'Assigned Location']]
    
    merged = merged.rename(columns = {'latMatched': "Latitude", 'lonMatched': "Longitude", 
                                    'timestamp': "Violation Time", 'speedMps': "Speed", "speed_limit": "Speed Limit"})
    
    merged['Speed Delta'] = merged['Speed'] - merged['Speed Limit']
    
    merged.sort_values(by = ['Vehicle', 'Violation Time'])
   
    merged.to_csv(directory + "violations-9-16.csv")
    print("Finished generating violations.csv")
    return merged

def getSummaryCSV(trip_report, event_report, points_df, vehicle_df):
    summary = pd.DataFrame() 
    
    # Get the # of trips, total distance, and total driven time (from the start time only, edge case)
    trip_report = trip_report[['Trip Start', 'Distance', 'Vehicle', 'delta_time']]
    trip_report['Date'] = trip_report['Trip Start'].apply(lambda x: str(x)[:-9])
    trip_report.drop("Trip Start", axis = 1, inplace = True)
    trip_report = trip_report.groupby(['Vehicle', 'Date']).agg(
                    num_of_trips = ('Vehicle', "count"),
                    total_distance = ('Distance', sum),
                    total_driven_time = ('delta_time', sum)
                    ).reset_index()
    
    # Get average and max speed from the data 
    points_df = points_df[["asset", "timestamp", "speed"]]
    points_df['Date'] = points_df['timestamp'].apply(lambda x: str(x)[:-9])
    points_df['asset_id'] = points_df['asset']
    points_df.drop("timestamp", axis = 1, inplace = True)
    points_df.drop("asset", axis = 1, inplace = True)
    points_df = points_df.merge(vehicle_df, on = 'asset_id', how = 'outer')
    points_df = points_df.groupby(["Vehicle", "Date", "Vehicle Name", "Vehicle Type", "Assigned Location"]).agg(
                        avg_speed = ('speed', "mean"),
                        max_speed = ('speed', max),
                    ).reset_index()
    # Remove the daily vehicle summary that has avg_speed < 1 
    points_df = points_df[points_df['avg_speed'] > 1]

    # Get the speeding incidents and speeding details 
    event_report = event_report[['Vehicle', 'Violation Time', 'Speed', 'Speed Limit']]
    event_report['Date'] = event_report['Violation Time'].apply(lambda x: str(x)[:-9])
    event_report.drop("Violation Time", axis = 1, inplace = True)
    
    event_report['speed_delta'] = event_report['Speed'] - event_report['Speed Limit']
    
    # Merge the reports 
    results = points_df.merge(trip_report, on = ['Vehicle', 'Date'], how = 'left')
    results = results.merge(event_report, on = ['Vehicle', 'Date'], how = 'outer').fillna(0)
    print("Finished generating summary.csv")
    results.to_csv(directory + "summary-9-16.csv")

def execute():
    # Get data from APIs 
    asset_points_list, vehicle_df = fetchAssetPointList()
    points_df = fetchAssetPoints(asset_points_list)
    
    if verbosity_level == 'vvv':
        print("Success in fetching vehicles & asset points!")
        
    points_df = processPoints(points_df)
    
    if verbosity_level == 'vvv':
        print("Success in processing asset points!")
        
    # Generates trip and speed data
    if verbosity_level == 'vvv' or verbosity_level == 'vv':
        print("Calculating trips ...")
        
    marks = markTrips(points_df)
    real_trips = getRealTrips(marks)
    
    if verbosity_level == 'vvv':
        print("Success in calculating trips!")
    
    if verbosity_level == 'vvv' or verbosity_level == 'vv':
        print("Calculating distance; generating violations events ...")
        
    distance, speed_limits, tracepoints = getDistanceAndEvents(real_trips, points_df)
    
    if verbosity_level == 'vvv':
        print("Success in getting distance, speed_limits and events!")
    
    print("Generating csv files ...")
    
    # Generates the reports 
    trip_report = getTripsCSV(distance, real_trips, vehicle_df)
    event_report = getEventsCSV(speed_limits, tracepoints, vehicle_df)
    getSummaryCSV(trip_report, event_report, points_df, vehicle_df)

    
execute()

if directory == '':
    directory = "current directory"
    
print("Finished generating to: " + directory)
