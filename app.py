from flask import Flask, render_template, request, jsonify
import os
import base64
from groq import Groq
import json
from dotenv import load_dotenv
import requests

load_dotenv()  # add this before the os.environ.get() lines

app = Flask(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
PLANT_API_KEY = os.environ.get("PLANT_API_KEY", "")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY", "")
client = Groq(api_key=GROQ_API_KEY)

# ─── PAGES ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

# ─── API: CROP ADVISORY ───────────────────────────────────────────────────────

@app.route("/api/crop-advisory", methods=["POST"])
def crop_advisory():
    data = request.json
    soil_type   = data.get("soil_type", "loamy")
    location    = data.get("location", "")
    season      = data.get("season", "Kharif")
    farm_size   = data.get("farm_size", "")
    prev_crop   = data.get("prev_crop", "")

    prompt = f"""You are an expert Indian agronomist. A farmer needs crop advisory.
Farm details:
- Location: {location}
- Soil Type: {soil_type}
- Season: {season}
- Farm Size: {farm_size} acres
- Previous Crop: {prev_crop}

Provide:
1. Top 3 recommended crops with reasoning
2. Sowing schedule
3. Fertilizer recommendations (NPK ratios)
4. Irrigation schedule
5. Expected yield estimate

Respond in JSON format:
{{
  "crops": [{{"name": "", "reason": "", "yield_estimate": ""}}],
  "sowing_schedule": "",
  "fertilizer": {{"N": "", "P": "", "K": "", "notes": ""}},
  "irrigation": "",
  "tips": []
}}"""

    result = call_claude(prompt)
    try:
        parsed = json.loads(result)
        return jsonify({"success": True, "data": parsed})
    except:
        return jsonify({"success": True, "data": {"raw": result}})


# ─── API: DISEASE DIAGNOSIS ───────────────────────────────────────────────────

@app.route("/api/disease-diagnosis", methods=["POST"])
def disease_diagnosis():

    if "image" not in request.files:
        return jsonify({
            "success": False,
            "error": "No image uploaded"
        })

    image = request.files["image"]

    response = requests.post(
        "https://plant.id/api/v3/health_assessment",
        headers={
            "Api-Key": PLANT_API_KEY
        },
        files={
            "images": image
        }
    )

    return jsonify(response.json())


# ─── API: WEATHER ─────────────────────────────────────────────────────────────

@app.route("/api/weather", methods=["GET"])
def weather():

    city = request.args.get("city", "Delhi")

    try:
        r = requests.get(
            f"http://api.weatherapi.com/v1/current.json?key={WEATHER_API_KEY}&q={city}"
        )

        data = r.json()

        weather_data = {
            "city": data["location"]["name"],
            "temp": data["current"]["temp_c"],
            "humidity": data["current"]["humidity"],
            "description": data["current"]["condition"]["text"],
            "wind_speed": data["current"]["wind_kph"]
        }

        advice = call_claude(
            f"""
            Weather:
            {weather_data}

            Give short farming advice.
            """
        )

        weather_data["farming_advice"] = advice

        return jsonify({
            "success": True,
            "data": weather_data
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })


# ─── API: MARKET PRICES ───────────────────────────────────────────────────────

@app.route("/api/market-prices", methods=["GET"])
def market_prices():
    crop = request.args.get("crop", "wheat")
    state = request.args.get("state", "Uttar Pradesh")

    prompt = f"""Provide current approximate mandi (market) prices for {crop} in {state}, India.
Format as JSON:
{{
  "crop": "{crop}",
  "state": "{state}",
  "min_price": 0,
  "max_price": 0,
  "modal_price": 0,
  "unit": "per quintal",
  "currency": "INR",
  "trend": "rising/falling/stable",
  "best_mandis": [{{"name": "", "price": 0}}],
  "advice": ""
}}
Use realistic 2024-2025 MSP and market data."""

    result = call_claude(prompt)
    try:
        parsed = json.loads(result)
        return jsonify({"success": True, "data": parsed})
    except:
        return jsonify({"success": True, "data": {"raw": result}})


# ─── API: CHATBOT ─────────────────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json

    message = data.get("message", "")
    lang = data.get("lang", "en")

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": f"You are Kishan Copilot. Reply in {'Hindi' if lang == 'hi' else 'English'}."
                },
                {
                    "role": "user",
                    "content": message
                }
            ],
            temperature=0.5,
            max_tokens=600
        )

        return jsonify({
            "success": True,
            "reply": response.choices[0].message.content
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })


# ─── API: GOVT SCHEMES ────────────────────────────────────────────────────────

@app.route("/api/schemes", methods=["GET"])
def govt_schemes():
    category = request.args.get("category", "all")
    prompt = f"""List 5 important Indian government schemes for farmers{' related to ' + category if category != 'all' else ''}.
JSON format:
{{
  "schemes": [{{
    "name": "",
    "ministry": "",
    "benefit": "",
    "eligibility": "",
    "how_to_apply": "",
    "link": ""
  }}]
}}"""
    result = call_claude(prompt)
    try:
        return jsonify({"success": True, "data": json.loads(result)})
    except:
        return jsonify({"success": True, "data": {"raw": result}})


# ─── HELPER ───────────────────────────────────────────────────────────────────

def call_claude(prompt, lang="en"):
    try:
        system_msg = f"""
        You are Kishan Copilot, an AI agriculture assistant for Indian farmers.
        Reply in {'Hindi' if lang == 'hi' else 'English'}.
        Keep responses practical and concise.
        """

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4,
            max_tokens=1000
        )

        return response.choices[0].message.content

    except Exception as e:
        return json.dumps({
            "error": str(e)
        })


if __name__ == "__main__":
    app.run(debug=True, port=5000)
