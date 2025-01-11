import pandas as pd
from django.shortcuts import render
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from math import ceil

# Load fuel prices CSV
FUEL_DATA_PATH = 'fuel-prices-for-be-assessment.csv'
fuel_data = pd.read_csv(FUEL_DATA_PATH)

@csrf_exempt
def optimize_route(request):
    start_location = request.GET.get('start')
    end_location = request.GET.get('end')

    if not start_location or not end_location:
        return JsonResponse({'error': 'Please provide start and end locations'}, status=400)

    # Convert the coordinates from string to the correct format (split by comma and ensure float conversion)
    try:
        start_coords = [float(coord) for coord in start_location.split(',')]
        end_coords = [float(coord) for coord in end_location.split(',')]
    except ValueError:
        return JsonResponse({'error': 'Invalid coordinates format'}, status=400)

    # Reverse geocoding to get place names
    REVERSE_GEOCODING_API = 'https://api.openrouteservice.org/geocode/reverse'
    MAP_API_KEY = '5b3ce3597851110001cf624836513257368a488f9ca003c58dc52eea'
    headers = {'Authorization': MAP_API_KEY}

    # Get start location name
    start_response = requests.get(REVERSE_GEOCODING_API, headers=headers, params={
        'point.lat': start_coords[1],
        'point.lon': start_coords[0],
        'size': 1
    })
    start_place = start_response.json().get('features', [{}])[0].get('properties', {}).get('label', 'Unknown Location')

    # Get end location name
    end_response = requests.get(REVERSE_GEOCODING_API, headers=headers, params={
        'point.lat': end_coords[1],
        'point.lon': end_coords[0],
        'size': 1
    })
    end_place = end_response.json().get('features', [{}])[0].get('properties', {}).get('label', 'Unknown Location')

    # Use a free API for route data
    MAP_API_URL = 'https://api.openrouteservice.org/v2/directions/driving-car'
    payload = {'coordinates': [start_coords, end_coords]}
    response = requests.post(MAP_API_URL, headers=headers, json=payload)
    route_data = response.json()

    # Check if the response contains an error
    if 'error' in route_data:
        error_message = route_data['error'].get('message', 'Unknown error')
        return JsonResponse({'error': error_message}, status=500)

    # Ensure 'routes' key exists and contains valid data
    if 'routes' not in route_data or len(route_data['routes']) == 0:
        return JsonResponse({'error': 'No route data found or invalid response format'}, status=500)

    # Extract route geometry and distance
    route_geometry = route_data['routes'][0]['geometry']
    total_distance_meters = route_data['routes'][0]['summary']['distance']
    waypoints = route_data['routes'][0]['segments'][0]['steps']

    # Convert distance to miles
    total_distance_miles = total_distance_meters / 1609.34

    # Calculate fuel stops and cost
    fuel_efficiency = 10  # miles per gallon
    vehicle_range = 500  # miles
    total_gallons_needed = total_distance_miles / fuel_efficiency
    fuel_stops = ceil(total_distance_miles / vehicle_range)
    avg_fuel_price = fuel_data['Retail Price'].mean()
    total_fuel_cost = total_gallons_needed * avg_fuel_price

    # Identify optimal fuel stops along the route
    fuel_stops_info = []
    current_distance = 0
    for i, waypoint in enumerate(waypoints):
        current_distance += waypoint['distance'] / 1609.34  # Convert to miles
        if current_distance >= vehicle_range or i == len(waypoints) - 1:
            cheapest_fuel = fuel_data.iloc[fuel_data['Retail Price'].idxmin()]
            fuel_stops_info.append({
                'location': f"{cheapest_fuel['City']}, {cheapest_fuel['State']}",
                'price_per_gallon': cheapest_fuel['Retail Price'],
            })
            current_distance = 0

    # Pass the data to the HTML template
    context = {
        'start_place': start_place,
        'end_place': end_place,
        'route_geometry': route_geometry,
        'total_distance_miles': round(total_distance_miles, 2),
        'fuel_stops_info': fuel_stops_info,
        'total_fuel_cost': round(total_fuel_cost, 2),
    }
    return render(request, 'route_results.html', context)