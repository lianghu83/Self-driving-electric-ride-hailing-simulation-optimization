"""
Run taxi system simulation.
"""

import pandas as pd
import numpy as np
from gurobipy import tuplelist
from geopy.distance import great_circle
import math
import itertools
from copy import deepcopy
from datetime import datetime
from Parameters import *
from Dispatcher import *
#from MyFunctions import *
#from Classes_2 import *
import random
import os
import shutil
from matplotlib import pyplot as plt



#%%initiate big request status table
#select dataset
data_used = "10_16_requests_5%"
#read trip data
df = pd.read_csv('C:\\EAV Taxi Data\\Raw Data\\'+data_used+'.csv')
df.drop(['hack_license','vendor_id','rate_code','store_and_fwd_flag','passenger_count'], axis='columns', inplace=True)
df.columns
#change charging power to 50kW
df['CS_power'] = charging_power
#distance to charging station
df['CS_travel_time_in_mins'].describe()

Request = df.copy(deep=True)
Request['id'] = df.index
Request.index = Request['id']
#adjust Request table
Request.drop(['medallion', 'trip_time_in_secs', 'CS_power'], axis='columns', inplace=True)    
Request = Request[['id','pickup_datetime','pickup_longitude','pickup_latitude',\
                   'trip_distance','trip_time_in_mins','dropoff_datetime','dropoff_longitude',\
                   'dropoff_latitude','CS_distance','CS_travel_time_in_mins','CS_longitude','CS_latitude','date']]
Request.columns = ['id','origin_timestamp','origin_longitude','origin_latitude',\
                   'trip_distance','trip_time','destination_timestamp','destination_longitude',\
                   'destination_latitude','cs_distance','cs_travel_time','cs_longitude','cs_latitude','date']
# randomly selected 100 requests
Request = Request.sample(n=100, random_state=1992)
# randomly assign waiting time
np.random.seed(83)
Request['wait_time'] = np.random.randint(0, 16, Request.shape[0])
Request['wait_time'].describe()
Request['served'] = False
Request['served_taxi'] = -1
Request['taxi_pickup_time'] = -1
Request['pickup_timestamp'] = -1
Request['dropoff_timestamp'] = -1
Request_col = Request.columns.tolist()
Request['cs_distance'].describe()

#request get rejected at a time interval
def getRejected(request_id):
    Request['wait_time'][request_id] += 1
    
#request get accepted, a taxi comes
def getAccepted(request_id, medallion, taxi_pickup_time):
    Request['wait_time'][request_id] += taxi_pickup_time
    Request['served'][request_id] = True
    Request['served_taxi'][request_id] = medallion
    Request['taxi_pickup_time'][request_id] = taxi_pickup_time
    
#request is served by taxi    
def getServed(request_id, start_timestamp):
    Request['pickup_timestamp'][request_id] = start_timestamp
    Request['dropoff_timestamp'][request_id] = start_timestamp + Request['trip_time'][request_id]*60

#%%initiate big taxi status table
data_used = "10_16_taxis_5%"
df = pd.read_csv('C:\\EAV Taxi Data\\Raw Data\\'+data_used+'.csv') 
#drop 2013000000
df['medallion'] = df['medallion'] % 2013000000
    
medallion = sorted(list(set(df['medallion'])))
# randomly select 100 taxis
np.random.seed(611)
medallion = sorted(list(np.random.choice(medallion, 100, replace=False)))

#create big taxi status table
Taxi = pd.DataFrame(columns=['medallion','status','start_timestamp','start_longitude',\
                             'start_latitude','start_range','status_distance','status_time',\
                             'end_timestamp','end_longitude','end_latitude','end_range'])
#initiate the taxi status table
random.seed(1991)    
for i in range(len(medallion)):
    each_taxi = df[df['medallion']==medallion[i]]
    each_taxi = each_taxi.sort_values(['pickup_datetime'])
    each_taxi = each_taxi.reset_index(drop=True)
    Taxi.loc[i, 'medallion'] = medallion[i]
    Taxi.loc[i, 'status'] = 'waiting'
    Taxi.loc[i, 'start_timestamp'] = start_time
    Taxi.loc[i, 'start_longitude'] = each_taxi.loc[0, 'pickup_longitude']
    Taxi.loc[i, 'start_latitude'] = each_taxi.loc[0, 'pickup_latitude']
    temp_range = random.uniform(low_range, EV_range)
    Taxi.loc[i, 'start_range'] = temp_range
    Taxi.loc[i, 'status_distance'] = 0.0
    Taxi.loc[i, 'status_time'] = -1
    Taxi.loc[i, 'end_timestamp'] = -1
    Taxi.loc[i, 'end_longitude'] = each_taxi.loc[0, 'pickup_longitude']
    Taxi.loc[i, 'end_latitude'] = each_taxi.loc[0, 'pickup_latitude']
    Taxi.loc[i, 'end_range'] = temp_range
Taxi.index = medallion
Taxi_col = Taxi.columns.tolist()
Taxi['start_range'].describe()
Taxi.dtypes

#create a taxi activity table to store all activities
#Taxi_activities = Taxi.copy(deep=True)
#Taxi_activities = Taxi_activities.reset_index(drop=True)

#taxi wait at somewhere
def startWaiting(medallion, timestamp):
    which_taxi = Taxi.loc[medallion]
    which_taxi['status'] = 'waiting'
    which_taxi['start_timestamp'] = timestamp
    which_taxi['start_longitude'] = which_taxi['end_longitude']
    which_taxi['start_latitude'] = which_taxi['end_latitude']
    which_taxi['start_range'] = which_taxi['end_range']
    which_taxi['status_distance'] = 0.0
    which_taxi['status_time'] = -1
    which_taxi['end_timestamp'] = -1
    which_taxi['end_longitude'] = which_taxi['start_longitude']
    which_taxi['end_latitude'] = which_taxi['start_latitude']
    which_taxi['end_range'] = which_taxi['start_range']
    Taxi.update(which_taxi)
    #global Taxi_activities
    #Taxi_activities = Taxi_activities.append(which_taxi, ignore_index=True)

#taxi gets called to pickup customer
def getCalled(medallion, request_id, timestamp, taxi_pickup_dist, taxi_pickup_time):
    which_taxi = Taxi.loc[medallion]
    which_request = Request.loc[request_id][['origin_longitude', 'origin_latitude']]
    which_taxi['status'] = 'called'
    which_taxi['start_timestamp'] = timestamp
    which_taxi['start_longitude'] = which_taxi['end_longitude']
    which_taxi['start_latitude'] = which_taxi['end_latitude']
    which_taxi['start_range'] = which_taxi['end_range']
    which_taxi['status_distance'] = taxi_pickup_dist
    which_taxi['status_time'] = taxi_pickup_time
    which_taxi['end_timestamp'] = which_taxi['start_timestamp'] + taxi_pickup_time*60
    which_taxi['end_longitude'] = which_request['origin_longitude']
    which_taxi['end_latitude'] = which_request['origin_latitude']
    which_taxi['end_range'] = which_taxi['start_range'] - taxi_pickup_dist
    Taxi.update(which_taxi)
    #global Taxi_activities
    #Taxi_activities = Taxi_activities.append(which_taxi, ignore_index=True)

#taxi serves customer
def serveCustomer(medallion, request_id, timestamp):
    which_taxi = Taxi.loc[medallion]
    which_request = Request.loc[request_id][['trip_distance', 'trip_time', 'destination_longitude', 'destination_latitude']]
    which_taxi['status'] = 'occupied'
    which_taxi['start_timestamp'] = timestamp
    which_taxi['start_longitude'] = which_taxi['end_longitude']
    which_taxi['start_latitude'] = which_taxi['end_latitude']
    which_taxi['start_range'] = which_taxi['end_range']
    which_taxi['status_distance'] = which_request['trip_distance']
    which_taxi['status_time'] = which_request['trip_time']
    which_taxi['end_timestamp'] = which_taxi['start_timestamp'] + which_taxi['status_time']*60
    which_taxi['end_longitude'] = which_request['destination_longitude']
    which_taxi['end_latitude'] = which_request['destination_latitude']
    which_taxi['end_range'] = which_taxi['start_range'] - which_taxi['status_distance']
    Taxi.update(which_taxi)
    #global Taxi_activities
    #Taxi_activities = Taxi_activities.append(which_taxi, ignore_index=True)

#taxi goes to charging station
def goToCharging(medallion, request_id, timestamp):
    which_taxi = Taxi.loc[medallion]
    which_request = Request.loc[request_id][['cs_distance', 'cs_travel_time', 'cs_longitude', 'cs_latitude']]
    which_taxi['status'] = 'go charging'
    which_taxi['start_timestamp'] = timestamp
    which_taxi['start_longitude'] = which_taxi['end_longitude']
    which_taxi['start_latitude'] = which_taxi['end_latitude']
    which_taxi['start_range'] = which_taxi['end_range']
    which_taxi['status_distance'] =  which_request['cs_distance']
    which_taxi['status_time'] =  which_request['cs_travel_time']
    which_taxi['end_timestamp'] = which_taxi['start_timestamp'] + which_taxi['status_time']*60
    which_taxi['end_longitude'] =  which_request['cs_longitude']
    which_taxi['end_latitude'] =  which_request['cs_latitude']
    which_taxi['end_range'] = which_taxi['start_range'] - which_taxi['status_distance']
    Taxi.update(which_taxi)
    #global Taxi_activities
    #Taxi_activities = Taxi_activities.append(which_taxi, ignore_index=True)

#taxi starts charging
def startCharging(medallion, timestamp):
    which_taxi = Taxi.loc[medallion]
    which_taxi['status'] = 'start charging'
    which_taxi['start_timestamp'] = timestamp
    which_taxi['start_longitude'] = which_taxi['end_longitude']
    which_taxi['start_latitude'] = which_taxi['end_latitude']
    which_taxi['start_range'] = which_taxi['end_range']
    which_taxi['status_distance'] = 0.0
    which_taxi['status_time'] = -1
    which_taxi['end_timestamp'] = -1 #self.start_timestamp + self.status_time*60
    which_taxi['end_longitude'] = which_taxi['start_longitude']
    which_taxi['end_latitude'] = which_taxi['start_latitude']
    which_taxi['end_range'] = which_taxi['start_range']
    Taxi.update(which_taxi)
    #global Taxi_activities
    #Taxi_activities = Taxi_activities.append(which_taxi, ignore_index=True)

#taxi ends charging
def endCharging(medallion, timestamp):
    which_taxi = Taxi.loc[medallion]
    which_taxi['status'] = 'waiting'
    add_range = min((timestamp-which_taxi['start_timestamp'])/3600*charging_power/electricity_consumption_rate, EV_range-which_taxi['start_range'])
    which_taxi['start_timestamp'] = timestamp
    which_taxi['start_longitude'] = which_taxi['end_longitude']
    which_taxi['start_latitude'] = which_taxi['end_latitude']
    which_taxi['start_range'] = which_taxi['start_range'] + add_range
    which_taxi['status_distance'] = 0.0
    which_taxi['status_time'] = -1
    which_taxi['end_timestamp'] = -1
    which_taxi['end_longitude'] = which_taxi['start_longitude']
    which_taxi['end_latitude'] = which_taxi['start_latitude']
    which_taxi['end_range'] = which_taxi['start_range']
    Taxi.update(which_taxi)
    #global Taxi_activities
    #Taxi_activities = Taxi_activities.append(which_taxi, ignore_index=True)

#%% Check taxi and request locations
plt.scatter(x=Request['origin_longitude'], y=Request['origin_latitude'], color='r')
plt.scatter(x=Taxi['start_longitude'], y=Taxi['start_latitude'])
plt.show()

#%%
taxi_sub = Taxi.copy()
taxi_sub_index = taxi_sub.index.tolist()
taxi_sub = taxi_sub.to_dict(orient="index")

request_sub = Request.copy()

### Preparation for dispatch ###
#get index, as keys for dictionary
request_sub_index = request_sub.index.tolist()
match_path = tuplelist(list(itertools.product(taxi_sub_index, request_sub_index)))

#convert dataframe into dictionary
request_sub = request_sub.to_dict(orient="index")

#calculate pickup distance dictionary
pickup_distance = pd.DataFrame(index=taxi_sub_index, columns=request_sub_index)
pickup_distance = pickup_distance.to_dict(orient="index")
for each_taxi in taxi_sub_index:
    for each_request in request_sub_index:
        taxi_GPS = (taxi_sub[each_taxi]['end_latitude'], taxi_sub[each_taxi]['end_longitude']) #latitude first
        request_GPS = (request_sub[each_request]['origin_latitude'], request_sub[each_request]['origin_longitude'])
        pickup_distance[each_taxi][each_request] = 1.4413*great_circle(taxi_GPS, request_GPS).miles + 0.1383 #miles

#calculate pickup time dictionary
pickup_time_in_mins = deepcopy(pickup_distance)
for each_taxi in taxi_sub_index:
    for each_request in request_sub_index:
        pickup_time_in_mins[each_taxi][each_request] = int(math.ceil(
                pickup_time_in_mins[each_taxi][each_request]/speed_average_NYC*60))
         
### Apply dispatch rules ###

#CENTRALIZED OPTIMIZATION with different weights for waiting time
from Dispatcher import CentralizedOptimization4_WaitTime_2p0    
v_op, obj_value = CentralizedOptimization4_WaitTime_2p0(taxi_sub,
                                 taxi_sub_index,
                                 request_sub,
                                 request_sub_index,
                                 match_path,
                                 pickup_distance,
                                 pickup_time_in_mins)   

### Update taxi status and request status for CENTRALIZED OPTIMIZATION ###

#(1) when taxi-request match
for each_taxi in taxi_sub_index:
    for each_request in request_sub_index:
        if (v_op[each_taxi][each_request]==1):
            #excute dispatch actions
            if Taxi['status'][each_taxi]=='start charging':
                endCharging(each_taxi, start_time) #use start_time to replace time_range[j]
            pickup_time_taxi_request = pickup_time_in_mins[each_taxi][each_request]
            getCalled(each_taxi, each_request, start_time,\
                      pickup_distance[each_taxi][each_request],\
                      pickup_time_taxi_request) #use start_time to replace time_range[j]
            getAccepted(each_request, each_taxi, pickup_time_taxi_request)
            serveCustomer(each_taxi, each_request, Taxi['end_timestamp'][each_taxi])
            getServed(each_request, Taxi['start_timestamp'][each_taxi])
            #check charging
            if (Request['cs_distance'][each_request] <= Taxi['end_range'][each_taxi] <= low_range):
                goToCharging(each_taxi, each_request, Taxi['end_timestamp'][each_taxi])
                startCharging(each_taxi, Taxi['end_timestamp'][each_taxi])
            else:
                startWaiting(each_taxi, Taxi['end_timestamp'][each_taxi])

#(3) when request not accepted
for each_request in request_sub_index:
    v_sum = 0
    for each_taxi in taxi_sub_index:
        v_sum += v_op[each_taxi][each_request]  
    if (v_sum==0):
        getRejected(each_request)


#Request.to_csv('C:\\EAV Taxi Data\\'+scenario+'\\request_different_wait.csv', index=False)

request = Request.copy()
request.to_csv('C:\\EAV Taxi Data\\10_16_no_wait\\request_2p0.csv', index=False)

#%% Evaluate system efficiency and equity among customers

request = pd.read_csv('C:\\EAV Taxi Data\\10_16_no_wait\\request_2p0.csv')

request['served'].describe()
request[request['served']==True].shape[0]/request.shape[0]

request_rej = request[request['served']==False]
request = request[request['served']==True]

request['wait_time_before_accepted'] = request['wait_time']-request['taxi_pickup_time']
request['wait_time_before_accepted'].describe()
request['wait_time'].describe()
request['taxi_pickup_time'].describe()

# Gini coefficient
def gini(list_of_values):
    sorted_list = sorted(list_of_values)
    height, area = 0, 0
    for value in sorted_list:
        height += value
        area += height - value / 2.
    fair_area = height * len(list_of_values) / 2.
    return (fair_area - area) / fair_area

gini(request['wait_time_before_accepted'])



#%% Plot1

t = [0,0.5,1,1.5,2]
data1 = [3.79,4.25,4.39,4.45,4.45]
data2 = [0.368,0.303,0.282,0.276,0.276]

fig, ax1 = plt.subplots(figsize=(5, 3))

color = 'tab:red'
ax1.set_xlabel('$\it{\u03B7}$')
ax1.set_ylabel('Avg. pickup time (min)', color=color)
line1 = ax1.plot(t, data1, color=color, linestyle='-')
ax1.tick_params(axis='y', labelcolor=color)
ax1.invert_yaxis()

ax2 = ax1.twinx()  # instantiate a second axes that shares the same x-axis

color = 'tab:green'
ax2.set_ylabel('Gini coefficient', color=color)  # we already handled the x-label with ax1
line2 = ax2.plot(t, data2, color=color, linestyle='--')
ax2.tick_params(axis='y', labelcolor=color)
ax2.invert_yaxis()

#plt.legend((line1, line2), ('1','2'))
fig.tight_layout()  # otherwise the right y-label is slightly clipped
plt.show()
fig.savefig("C:\\EAV Taxi Data\\"+'10_16_no_wait'+"\\compare_gini_1"+".jpg", dpi=300)



#%% Plot2

t = [0,0.5,1,1.5,2]
data1 = [3.79,4.25,4.39,4.45,4.45]
data2 = [0.368,0.303,0.282,0.276,0.276]

fig, ax1 = plt.subplots(figsize=(5, 3))

color = 'tab:red'
ax1.set_xlabel('$\it{\u03B7}$')
ax1.set_ylabel('Avg. pickup time (min)')
line1 = ax1.plot(t, data1, color=color, linestyle='-')
ax1.tick_params(axis='y')
#ax1.invert_yaxis()

ax2 = ax1.twinx()  # instantiate a second axes that shares the same x-axis

color = 'tab:green'
ax2.set_ylabel('Gini coefficient')  # we already handled the x-label with ax1
line2 = ax2.plot(t, data2, color=color, linestyle='--')
ax2.tick_params(axis='y')
#ax2.invert_yaxis()

ax1.xaxis.grid(linestyle=':')
fig.legend(('Avg. pickup time','Gini coefficient'), loc='upper right', bbox_to_anchor=(0.85,0.7), framealpha=1)

fig.tight_layout()  # otherwise the right y-label is slightly clipped
plt.show()
fig.savefig("C:\\EAV Taxi Data\\"+'10_16_no_wait'+"\\compare_gini_2"+".jpg", dpi=300)



#%% Plot3
data1 = [3.79,4.25,4.39,4.45,4.45]
data2 = [0.368,0.303,0.282,0.276,0.276]

fig = plt.figure(figsize=(5, 3))
plt.plot(data2, data1, marker='o', color='red')
plt.xlabel('Gini Coefficient')
plt.ylabel('Avg. pickup time (min)')
plt.gca().invert_xaxis()
plt.gca().invert_yaxis()
plt.tight_layout()
plt.show()

fig.savefig("C:\\EAV Taxi Data\\"+'10_16_no_wait'+"\\compare_gini_3"+".jpg", dpi=300)









