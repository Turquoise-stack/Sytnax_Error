from flask import Flask, request, jsonify
import requests
import os
from flask_cors import CORS

app = Flask(__name__)
CORS(app)


def google_search(query):
    google_api_key = os.getenv('GOOGLE_API_KEY')
    if "electricity" in query.lower():
        google_search_engine_id = os.getenv('GOOGLE_SEARCH_ENGINE_ID_ELECTRICTY')
    else:
        google_search_engine_id = os.getenv('GOOGLE_SEARCH_ENGINE_ID')
    
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": google_api_key,
        "cx": google_search_engine_id,
        "q": query
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        return None

@app.route('/search-google', methods=['POST'])
def search_google():
    request_data = request.get_json()
    query = request_data.get('query', '')

    if not query:
        return jsonify({"error": "Query parameter is required"}), 400

    search_results = google_search(query)

    if search_results:
        html_snippet = search_results['items'][0]['htmlSnippet'] if 'items' in search_results and search_results['items'] else ''
        
        return jsonify({"status": "success", "html_snippet": html_snippet})
    else:
        return jsonify({"status": "error", "message": "Failed to fetch search results"}), 500


    
def fetch_pvgis_data(latitude, longitude, peakpower, loss):
    url = "https://re.jrc.ec.europa.eu/api/PVcalc"
    params = {
        "lat": latitude,
        "lon": longitude,
        "peakpower": peakpower,
        "loss": loss,
        "outputformat": "json" 
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()  
    else:
        return None

def extract_energy_production(data):
    if data and "outputs" in data and "monthly" in data["outputs"] and "totals" in data["outputs"]:
        monthly_data = data["outputs"]["monthly"]["fixed"]
        yearly_data = data["outputs"]["totals"]["fixed"]["E_y"]
        
        monthly_production = {item["month"]: item["E_m"] for item in monthly_data}
        
        return {
            "yearly_energy_production": yearly_data,
            "monthly_energy_production": monthly_production
        }
    else:
        return None

@app.route('/api/pvgis/<float:lat>/<float:lon>/<float:peakpower>', methods=['GET'])
def get_pvgis_data(lat, lon, peakpower):
    latitude = lat
    longitude = lon
    peakpower = peakpower

    data = fetch_pvgis_data(latitude, longitude, peakpower, 14)
    energy_data = extract_energy_production(data)
    print(energy_data)
    if energy_data:
        return jsonify({"status": "success", "data": energy_data})
    else:
        return jsonify({"status": "error", "message": "Failed to fetch data"}), 400

def fetch_openai_completion(prompt):
    url = "https://api.openai.com/v1/chat/completions" 
    headers = {
        "Authorization": f"Bearer {os.getenv('API_KEY')}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-4o", 
        "messages": [
            {
                "role": "system",
                "content": prompt
            }
        ],
        "max_tokens": 200
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json()
    else:
        return response.json()

@app.route('/api/openai/describe', methods=['POST'])
def describe_roi():
    data = request.get_json()
    prompt = data.get("prompt", "")
    roi_int = data.get("roi_int", 0)
    yearly_production = data.get("yearly_production", 0)
    peakpower = data.get("peakpower", 0.0)
    yearly_production_in_dollars = data.get("yearly_production_in_dollars", 0)
    total_solar_cost = data.get("total_solar_cost", 0)
    country = data.get("country", "")

    if not prompt:
        return jsonify({"status": "error", "message": "Prompt is required"}), 400

    if "describe" in prompt.lower():
        openai_prompt = (
            f"Apporach like an advisor and be cheerful. Start talking like you started to introducing me the numbers. Do not answer to me directly just do what I say in following. Describe the return on investment based on these parameters for solar panel installation and give investment comment if person should go in or not. "
            f"how long it takes to return its investment as years: {roi_int}, yearly production: {yearly_production} kWh, peak power in kW: {peakpower}, "
            f"yearly production in dollars: ${yearly_production_in_dollars}, total solar cost: ${total_solar_cost}, "
            f"country: {country}."
        )

        completion = fetch_openai_completion(openai_prompt)

        if completion and 'choices' in completion and len(completion['choices']) > 0:
            message = completion['choices'][0].get('message')
            if message and 'content' in message:
                content = message['content']
                return jsonify({"status": "success", "content": content})
            else:
                app.logger.error("Missing 'content' in the completion response")
        else:
            app.logger.error("Invalid 'choices' structure in the completion response")

        return jsonify

@app.route('/api/openai/completion', methods=['POST'])
def openai_completion():
    data = request.get_json()
    prompt = data.get("prompt", "")

    if not prompt:
        return jsonify({"status": "error", "message": "Prompt is required"}), 400
            

    query = prompt  
    search_results = google_search(query)
    if not search_results:
        return jsonify({"status": "error", "message": "Failed to fetch search results from Google"}), 500

    html_snippet = search_results['items'][0]['htmlSnippet']  
    print(html_snippet)

    openai_prompt = f"Use the following information to parse the $ per watt and only but only return the price but nothing else. Here is the info to parse: {html_snippet}"
    print(openai_prompt)

    completion = fetch_openai_completion(openai_prompt)
    print(completion)

    if completion and 'choices' in completion and len(completion['choices']) > 0:
        message = completion['choices'][0].get('message')
        if message and 'content' in message:
            content = message['content']
            return jsonify({"status": "success", "content": content})
        else:
            app.logger.error("Missing 'content' in the completion response")
    else:
        app.logger.error("Invalid 'choices' structure in the completion response")

    return jsonify({"status": "error", "message": "Failed to generate completion from OpenAI"}), 500



def get_country_from_coordinates(latitude, longitude):
    google_maps_api_key = os.getenv('GOOGLE_MAPS_API_KEY')
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "latlng": f"{latitude},{longitude}",
        "key": google_maps_api_key
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        if data['status'] == 'OK' and len(data['results']) > 0:
            for component in data['results'][0]['address_components']:
                if 'country' in component['types']:
                    return component['long_name']
        else:
            return None
    else:
        return None

@app.route('/get_coordinates', methods=['POST'])
def get_coordinates():
    data = request.json
    address = data.get('address')
    if not address:
        return jsonify({"error": "Address not provided"}), 400
    
    google_maps_api_key = os.getenv('GOOGLE_MAPS_API_KEY')
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={google_maps_api_key}"
    
    response = requests.get(url)
    if response.status_code == 200:
        results = response.json().get('results')
        if results:
            location = results[0]['geometry']['location']
            address_components = results[0]['address_components']
            
            country = None
            for component in address_components:
                if 'country' in component['types']:
                    country = component['long_name']
                    break
            
            return jsonify({
                "address": address,
                "latitude": location['lat'],
                "longitude": location['lng'],
                "country": country
            })
        else:
            return jsonify({"error": "No results found"}), 404
    else:
        return jsonify({"error": "Error fetching data from Google Maps API"}), response.status_code


@app.route('/api/browse', methods=['POST'])
def browse():
    data = request.get_json()
    address = data.get('address', '')
    peakpower = data.get('peakpower', 0.0)

    if not address or not peakpower:
        return jsonify({"status": "error", "message": "Both 'address' and 'peakpower' parameters are required"}), 400

    response = requests.post('http://localhost:5000/get_coordinates', json={'address': address})
    
    if response.status_code == 200:
        coordinates = response.json()
        latitude = coordinates.get('latitude')
        longitude = coordinates.get('longitude')
        country = coordinates.get('country')

        if not latitude or not longitude:
            return jsonify({"status": "error", "message": "Failed to get coordinates"}), 500
    else:
        return jsonify({"status": "error", "message": "Error fetching coordinates from /get_coordinates"}), response.status_code

    response2 = requests.get(f'http://127.0.0.1:5000/api/pvgis/{latitude}/{longitude}/{peakpower}.0')

    if response2.status_code == 200:
        data2 = response2.json()
        yearly_production = data2["data"].get("yearly_energy_production")
        monthly_production = data2["data"].get("monthly_energy_production")
        if not yearly_production or not monthly_production:
            return jsonify({"status": "error", "message": "Failed to get production"}), 500
    else:
        return jsonify({"status": "error", "message": "Error "}), response.status_code
    
    response3 = requests.post(f'http://127.0.0.1:5000/api/openai/completion', json={'prompt': f"solar installation cost in {country}"})
    if response3.status_code == 200:
        openai_solar_response = response3.json()
        solar_cost_per_watt = openai_solar_response.get("content")
        solar_cost_kilowatt = float(solar_cost_per_watt) * 1000
        total_solar_cost = solar_cost_kilowatt * peakpower
        if not solar_cost_per_watt or not solar_cost_kilowatt:
            return jsonify({"status": "error", "message": "Failed to get openai"}), 500    
    else:
        return jsonify({"status": "error", "message": "Error "}), response.status_code
    
    response4 = requests.post(f'http://127.0.0.1:5000/api/openai/completion', json={'prompt': f"electricity cost in {country}"})
    if response4.status_code == 200:
        openai_electricity_response = response4.json()
        electiricty_cost_per_kwh = openai_electricity_response.get("content")
        if not electiricty_cost_per_kwh:
            return jsonify({"status": "error", "message": "Failed to get openai"}), 500    
    else:
        return jsonify({"status": "error", "message": "Error "}), response.status_code
    
    yearly_production_in_dollars = yearly_production * float(electiricty_cost_per_kwh)
    roi = total_solar_cost/yearly_production_in_dollars
    roi_int = int(roi)

    response5 = requests.post(f'http://127.0.0.1:5000/api/openai/describe', json={
                                                                                "prompt": "Describe the return on investment for solar panel installation.",
                                                                                "roi_int": roi_int,
                                                                                "yearly_production": yearly_production,
                                                                                "peakpower": peakpower,
                                                                                "yearly_production_in_dollars": yearly_production_in_dollars,
                                                                                "total_solar_cost": total_solar_cost,
                                                                                "country": country
                                                                            })

    if response5.status_code == 200:
        openai_comment = response5.json()
        comment = openai_comment.get("content")
        if not comment:
            return jsonify({"status": "error", "message": "Failed to get openai"}), 500    
    else:
        return jsonify({"status": "error", "message": "Error "}), response.status_code

    return jsonify({
                    "Solar Installation Cost in USD":total_solar_cost,
                    "Yearly Production in USD": yearly_production_in_dollars,
                    "ROI":roi_int,
                    "Yearly kWh Production": yearly_production,
                    "Monthly kWh Production": monthly_production,
                    "Peak Power": peakpower,
                    "Address": address,
                    "Latitude": latitude,
                    "Longitude": longitude,
                    "Comment": comment,
                    })
    
if __name__ == '__main__':
    app.run(debug=True)




