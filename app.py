from flask import Flask, render_template, request, jsonify
import os
import base64
import requests
import json
from dotenv import load_dotenv

load_dotenv()  # add this before the os.environ.get() lines

app = Flask(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")

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
        return jsonify({"success": False, "error": "No image provided"}), 400

    img_file = request.files["image"]
    img_data = base64.b64encode(img_file.read()).decode("utf-8")
    media_type = img_file.content_type or "image/jpeg"

    crop_name = request.form.get("crop_name", "unknown crop")

    prompt = f"""You are a plant pathologist AI. Analyze this crop image for the crop: {crop_name}.
Identify any diseases, pests, or nutrient deficiencies visible.

Respond in JSON:
{{
  "disease_name": "",
  "confidence": "high/medium/low",
  "severity": "mild/moderate/severe",
  "symptoms": [],
  "cause": "",
  "treatment": {{
    "organic": [],
    "chemical": [],
    "preventive": []
  }},
  "urgency": "immediate/within_week/monitor"
}}"""

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1000,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img_data}},
                    {"type": "text", "text": prompt}
                ]
            }]
        }
    )
    result_text = response.json()["content"][0]["text"]
    try:
        parsed = json.loads(result_text)
        return jsonify({"success": True, "data": parsed})
    except:
        return jsonify({"success": True, "data": {"raw": result_text}})


# ─── API: WEATHER ─────────────────────────────────────────────────────────────

@app.route("/api/weather", methods=["GET"])
def weather():
    city = request.args.get("city", "Delhi")

    # Always return mock if API key missing or call fails
    def mock_weather():
        return jsonify({"success": True, "data": {
            "city": city, "temp": 32, "feels_like": 36,
            "humidity": 65, "description": "Partly Cloudy",
            "wind_speed": 12, "rain_probability": "30%",
            "farming_advice": "Good conditions for irrigation today."
        }})

    if not OPENWEATHER_API_KEY:
        return mock_weather()

    try:
        r = requests.get(
            f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric",
            timeout=5
        )
        w = r.json()
        if w.get("cod") != 200:
            return mock_weather()
        weather_data = {
            "city": city,
            "temp": round(w["main"]["temp"]),
            "feels_like": round(w["main"]["feels_like"]),
            "humidity": w["main"]["humidity"],
            "description": w["weather"][0]["description"].title(),
            "wind_speed": round(w["wind"].get("speed", 0) * 3.6),
            "rain_probability": str(w.get("clouds", {}).get("all", 0)) + "% cloud"
        }
        advice_prompt = f"Weather: {weather_data['description']}, Temp: {weather_data['temp']}°C. Give 1-sentence farming advice."
        weather_data["farming_advice"] = call_claude(advice_prompt)
        return jsonify({"success": True, "data": weather_data})
    except Exception as e:
        return mock_weather()


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
    history = data.get("history", [])
    lang = data.get("lang", "en")

    system = f"""You are Kishan Copilot, an AI farming assistant for Indian farmers.
You speak in {'Hindi' if lang == 'hi' else 'English'} and provide expert advice on:
- Crop selection and management
- Pest and disease control
- Weather and irrigation
- Government schemes (PM-KISAN, Kisan Credit Card, etc.)
- Market prices and selling strategies
Be concise, practical, and empathetic. Use simple language a farmer can understand."""

    messages = history + [{"role": "user", "content": message}]

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={"model": "claude-sonnet-4-20250514", "max_tokens": 600, "system": system, "messages": messages}
    )
    reply = response.json()["content"][0]["text"]
    return jsonify({"success": True, "reply": reply})


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

def call_claude(prompt):
    if not ANTHROPIC_API_KEY:
        return '{"error": "API key not configured. Set ANTHROPIC_API_KEY env variable."}'
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": prompt}]
        }
    )
    return response.json()["content"][0]["text"]


if __name__ == "__main__":
    app.run(debug=True, port=5000)
