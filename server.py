from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import time
import os
import joblib
import pandas as pd
import subprocess

from urllib.parse import urlencode, urlparse, parse_qs
from datetime import datetime


# ============================================================
# DATA.GOV.IN API
# ============================================================

API_KEY = "579b464db66ec23bdd000001a45abb90b19d48db76e87f2a09caffb2"

RESOURCE_ID = "35985678-0d79-46b4-9ed6-6f13308a1d24"

API_URL = f"https://api.data.gov.in/resource/{RESOURCE_ID}"


# ============================================================
# MODEL FILES
# ============================================================

MARKET_MODEL_FILE = "market_price_model.pkl"
MARKET_FEATURES_FILE = "market_price_features.pkl"


# ============================================================
# LOAD XGBOOST MODEL
# ============================================================

market_price_model = None
market_price_features = None

try:

    market_price_model = joblib.load(
        MARKET_MODEL_FILE
    )

    market_price_features = joblib.load(
        MARKET_FEATURES_FILE
    )

    print("Market price model loaded successfully.")
    print(
        "Expected features:",
        len(market_price_features)
    )

except Exception as error:

    print("WARNING: Market model could not be loaded.")
    print(error)


# ============================================================
# SENSOR DATA
# ============================================================

latest_data = {

    "moisture": None,
    "temperature": None,
    "ph": None,
    "n": None,
    "p": None,
    "k": None

}

last_update_time = None


# ============================================================
# SENSOR VALIDATION
# ============================================================

def sensor_data_available():

    required = [
        "moisture",
        "temperature",
        "ph",
        "n",
        "p",
        "k"
    ]

    if last_update_time is None:
        return False

    for field in required:

        value = latest_data.get(field)

        if value is None:
            return False

        try:
            float(value)
        except:
            return False

    return True


# ============================================================
# CROP RECOMMENDATION
# ============================================================

def recommend(data):

    # Keep your existing crop recommendation
    # implementation here if already connected.

    return []


# ============================================================
# MARKET API
# ============================================================

def get_market_data(commodity, state, district):

    if not commodity or not state or not district:
        return {
            "status": "error",
            "message": "State, District and Commodity are required."
        }

    print("\n==========================================")
    print("DATA.GOV.IN MARKET REQUEST")
    print("==========================================")
    print("State     :", state)
    print("District  :", district)
    print("Commodity :", commodity)

    # ---------------------------------------------------------
    # Try API with all 3 filters first
    # ---------------------------------------------------------

    params = [
        ("api-key", API_KEY),
        ("format", "json"),
        ("limit", "1000"),
        ("filters[State]", state),
        ("filters[District]", district),
        ("filters[Commodity]", commodity)
    ]

    url = API_URL + "?" + urlencode(params)

    try:

        result = subprocess.run(
            [
                "curl",
                "-sS",
                "--connect-timeout", "15",
                "--max-time", "120",
                "-H", "Accept: application/json",
                url
            ],
            capture_output=True,
            text=True
        )

        print("CURL RETURN CODE:", result.returncode)

        if result.returncode != 0:

            print("CURL ERROR:")
            print(result.stderr)

            return {
                "status": "error",
                "message": "Could not connect to data.gov.in."
            }

        raw_response = result.stdout.strip()

        if not raw_response:

            return {
                "status": "error",
                "message": "data.gov.in returned an empty response."
            }

        try:

            data = json.loads(raw_response)

        except json.JSONDecodeError:

            print("INVALID JSON:")
            print(raw_response[:2000])

            return {
                "status": "error",
                "message": "Invalid response received from data.gov.in."
            }

        if "error" in data:

            print("API ERROR:", data["error"])

            return {
                "status": "error",
                "message": str(data["error"])
            }

        records = data.get("records", [])

        print("Records returned by API:", len(records))

        # ---------------------------------------------------------
        # If API returned records, verify them locally
        # ---------------------------------------------------------

        def clean(value):
            return " ".join(
                str(value or "").strip().lower().split()
            )

        wanted_state = clean(state)
        wanted_district = clean(district)
        wanted_commodity = clean(commodity)

        matched = []

        for record in records:

            record_state = clean(
                record.get("State")
            )

            record_district = clean(
                record.get("District")
            )

            record_commodity = clean(
                record.get("Commodity")
            )

            if (
                record_state == wanted_state
                and
                record_district == wanted_district
                and
                record_commodity == wanted_commodity
            ):

                matched.append(record)

        # ---------------------------------------------------------
        # Partial commodity match
        # ---------------------------------------------------------

        if not matched:

            for record in records:

                record_state = clean(
                    record.get("State")
                )

                record_district = clean(
                    record.get("District")
                )

                record_commodity = clean(
                    record.get("Commodity")
                )

                if (
                    record_state == wanted_state
                    and
                    record_district == wanted_district
                    and
                    (
                        wanted_commodity in record_commodity
                        or
                        record_commodity in wanted_commodity
                    )
                ):

                    matched.append(record)

        print(
            "Matching records:",
            len(matched)
        )

        if not matched:

            available = sorted(
                set(
                    str(
                        r.get("Commodity", "")
                    ).strip()
                    for r in records
                    if r.get("Commodity")
                )
            )

            print(
                "Commodities returned by API:"
            )

            print(
                available[:100]
            )

            return {
                "status": "no_data",
                "message":
                    "No market records found for the selected State, District and Commodity."
            }

        # ---------------------------------------------------------
        # Sort newest first
        # ---------------------------------------------------------

        def get_date(record):

            value = record.get(
                "Arrival_Date"
            )

            try:

                return datetime.strptime(
                    str(value),
                    "%d/%m/%Y"
                )

            except:

                return datetime.min

        matched.sort(
            key=get_date,
            reverse=True
        )

        latest = matched[0]

        # ---------------------------------------------------------
        # Extract prices
        # ---------------------------------------------------------

        min_prices = []
        max_prices = []
        modal_prices = []

        for record in matched:

            try:

                value = float(
                    str(
                        record.get("Min_Price", "")
                    ).replace(",", "")
                )

                if value > 0:
                    min_prices.append(value)

            except:

                pass

            try:

                value = float(
                    str(
                        record.get("Max_Price", "")
                    ).replace(",", "")
                )

                if value > 0:
                    max_prices.append(value)

            except:

                pass

            try:

                value = float(
                    str(
                        record.get("Modal_Price", "")
                    ).replace(",", "")
                )

                if value > 0:
                    modal_prices.append(value)

            except:

                pass

        if (
            not min_prices
            or
            not max_prices
            or
            not modal_prices
        ):

            return {
                "status": "no_data",
                "message":
                    "Market records found, but price values are missing."
            }

        # ---------------------------------------------------------
        # Calculate values
        # ---------------------------------------------------------

        minimum_price = min(
            min_prices
        )

        maximum_price = max(
            max_prices
        )

        average_price = sum(
            modal_prices
        ) / len(modal_prices)

        # ---------------------------------------------------------
        # Helper
        # ---------------------------------------------------------

        def convert_price(value):

            try:

                return float(
                    str(value).replace(",", "")
                )

            except:

                return None

        # ---------------------------------------------------------
        # Return
        # ---------------------------------------------------------

        result = {

            "status": "ok",

            "date":
                latest.get(
                    "Arrival_Date",
                    "--"
                ),

            "commodity":
                latest.get(
                    "Commodity",
                    commodity
                ),

            "state":
                latest.get(
                    "State",
                    state
                ),

            "district":
                latest.get(
                    "District",
                    district
                ),

            "market":
                latest.get(
                    "Market",
                    "--"
                ),

            "variety":
                latest.get(
                    "Variety",
                    "--"
                ),

            "grade":
                latest.get(
                    "Grade",
                    "--"
                ),

            "min_price":
                round(
                    minimum_price,
                    2
                ),

            "max_price":
                round(
                    maximum_price,
                    2
                ),

            "average_price":
                round(
                    average_price,
                    2
                ),

            "modal_price":
                convert_price(
                    latest.get("Modal_Price")
                ),

            "record_count":
                len(matched),

            "model_min_price":
                convert_price(
                    latest.get("Min_Price")
                ),

            "model_max_price":
                convert_price(
                    latest.get("Max_Price")
                )
        }

        print("\n==========================================")
        print("MARKET RESULT")
        print("==========================================")
        print("Records :", result["record_count"])
        print("Minimum :", result["min_price"])
        print("Maximum :", result["max_price"])
        print("Average :", result["average_price"])
        print("Modal   :", result["modal_price"])
        print("Date    :", result["date"])

        return result

    except Exception as error:

        print("\nMARKET API ERROR:")
        print(error)

        return {
            "status": "error",
            "message": str(error)
        }

# ============================================================
# XGBOOST PREDICTION
# ============================================================

def predict_market_price(
    market_data
):

    if market_price_model is None:

        return {

            "status": "error",

            "message":
                "Market price model is not loaded."

        }


    if market_price_features is None:

        return {

            "status": "error",

            "message":
                "Market model features are not loaded."

        }


    try:

        arrival_date = market_data.get(
            "date"
        )

        commodity = market_data.get(
            "commodity"
        )

        district = market_data.get(
            "district"
        )

        market = market_data.get(
            "market"
        )

        state = market_data.get(
            "state"
        )

        variety = market_data.get(
            "variety"
        )

        grade = market_data.get(
            "grade"
        )


        min_price = market_data.get(
            "model_min_price"
        )

        max_price = market_data.get(
            "model_max_price"
        )


        # ====================================================
        # DATE
        # ====================================================

        parsed_date = pd.to_datetime(
            arrival_date,
            dayfirst=True,
            errors="coerce"
        )


        if pd.isna(parsed_date):

            return {

                "status": "error",

                "message":
                    "Invalid market arrival date."

            }


        # ====================================================
        # CREATE INPUT ROW
        # ====================================================

        row = pd.DataFrame([{

            "Commodity":
                commodity,

            "District":
                district,

            "Market":
                market,

            "State":
                state,

            "Variety":
                variety,

            "Grade":
                grade,

            "Min_Price":
                float(min_price),

            "Max_Price":
                float(max_price),

            "Year":
                parsed_date.year,

            "Month":
                parsed_date.month,

            "Day":
                parsed_date.day,

            "DayOfWeek":
                parsed_date.dayofweek

        }])


        # ====================================================
        # CATEGORICAL COLUMNS
        # ====================================================

        categorical_columns = [

            "Commodity",
            "District",
            "Market",
            "State",
            "Variety",
            "Grade"

        ]


        row = pd.get_dummies(

            row,

            columns=categorical_columns,

            dummy_na=True

        )


        # ====================================================
        # MATCH TRAINING FEATURES
        # ====================================================

        row = row.reindex(

            columns=market_price_features,

            fill_value=0

        )


        row = row.fillna(0)


        # ====================================================
        # XGBOOST PREDICTION
        # ====================================================

        prediction = market_price_model.predict(
            row
        )[0]


        prediction = float(
            prediction
        )


        if prediction < 0:

            prediction = 0


        print(
            "XGBoost Predicted Price:",
            prediction
        )


        return {

            "status": "ok",

            "predicted_modal_price":
                round(
                    prediction,
                    2
                )

        }


    except Exception as error:

        print("XGBOOST ERROR:")
        print(error)

        return {

            "status": "error",

            "message":
                str(error)

        }


# ============================================================
# SEND JSON
# ============================================================

def send_json(
    handler,
    response,
    status_code=200
):

    handler.send_response(
        status_code
    )

    handler.send_header(
        "Content-Type",
        "application/json; charset=utf-8"
    )

    handler.send_header(
        "Cache-Control",
        "no-store"
    )

    handler.end_headers()

    handler.wfile.write(

        json.dumps(
            response,
            ensure_ascii=False
        ).encode("utf-8")

    )


# ============================================================
# HTTP HANDLER
# ============================================================

class Handler(
    BaseHTTPRequestHandler
):


    # ========================================================
    # GET
    # ========================================================

    def do_GET(self):

        parsed = urlparse(
            self.path
        )

        path = parsed.path

        query = parse_qs(
            parsed.query
        )


        # ====================================================
        # INDEX
        # ====================================================

        if path == "/":

            try:

                with open(
                    "index.html",
                    "rb"
                ) as f:

                    content = f.read()


                self.send_response(200)

                self.send_header(
                    "Content-Type",
                    "text/html; charset=utf-8"
                )

                self.end_headers()

                self.wfile.write(
                    content
                )


            except Exception as error:

                self.send_error(
                    500,
                    str(error)
                )


        # ====================================================
        # CSS
        # ====================================================

        elif path == "/style.css":

            try:

                with open(
                    "style.css",
                    "rb"
                ) as f:

                    content = f.read()


                self.send_response(200)

                self.send_header(
                    "Content-Type",
                    "text/css; charset=utf-8"
                )

                self.end_headers()

                self.wfile.write(
                    content
                )


            except Exception as error:

                self.send_error(
                    500,
                    str(error)
                )


        # ====================================================
        # IMAGES
        # ====================================================

        elif path.startswith(
            "/images/"
        ):

            file_path = path.lstrip("/")


            if not os.path.exists(
                file_path
            ):

                self.send_error(404)

                return


            if file_path.endswith(
                ".jpg"
            ):

                content_type = "image/jpeg"

            elif file_path.endswith(
                ".png"
            ):

                content_type = "image/png"

            else:

                self.send_error(404)

                return


            with open(
                file_path,
                "rb"
            ) as f:

                content = f.read()


            self.send_response(200)

            self.send_header(
                "Content-Type",
                content_type
            )

            self.end_headers()

            self.wfile.write(
                content
            )


        # ====================================================
        # SENSOR DATA
        # ====================================================

        elif path == "/data":

            if not sensor_data_available():

                send_json(

                    self,

                    {

                        "status":
                            "no_data",

                        "message":
                            "Waiting for valid sensor data."

                    }

                )

                return


            response = {

                "status":
                    "ok",

                "moisture":
                    latest_data["moisture"],

                "temperature":
                    latest_data["temperature"],

                "ph":
                    latest_data["ph"],

                "n":
                    latest_data["n"],

                "p":
                    latest_data["p"],

                "k":
                    latest_data["k"],

                "crops":
                    recommend(
                        latest_data
                    )

            }


            send_json(
                self,
                response
            )


        # ====================================================
        # MARKET PRICE
        # ====================================================

        elif path == "/market-predict":

            state = query.get(
                "state",
                [""]
            )[0].strip()


            district = query.get(
                "district",
                [""]
            )[0].strip()


            commodity = query.get(
                "commodity",
                [""]
            )[0].strip()


            # =================================================
            # VALIDATE
            # =================================================

            if (
                not state or
                not district or
                not commodity
            ):

                send_json(

                    self,

                    {

                        "status":
                            "error",

                        "message":
                            "Please enter State, District and Commodity."

                    }

                )

                return


            # =================================================
            # GET DATA FROM DATA.GOV.IN
            # =================================================

            market_data = get_market_data(

                commodity,
                state,
                district

            )


            if market_data.get(
                "status"
            ) != "ok":

                send_json(
                    self,
                    market_data
                )

                return


            # =================================================
            # XGBOOST
            # =================================================

            prediction = predict_market_price(
                market_data
            )


            # =================================================
            # FINAL RESPONSE
            # =================================================

            response = {

                **market_data,

                "prediction":
                    prediction

            }


            send_json(
                self,
                response
            )


        # ====================================================
        # UNKNOWN ROUTE
        # ====================================================

        else:

            self.send_error(
                404
            )


    # ========================================================
    # POST
    # ========================================================

    def do_POST(self):

        global last_update_time


        if self.path != "/update":

            self.send_error(
                404
            )

            return


        try:

            content_length = int(

                self.headers.get(
                    "Content-Length",
                    "0"
                )

            )


            if content_length <= 0:

                send_json(

                    self,

                    {

                        "status":
                            "error",

                        "message":
                            "Empty request body."

                    },

                    400

                )

                return


            body = self.rfile.read(
                content_length
            )


            data = json.loads(
                body.decode("utf-8")
            )


            print()
            print(
                "Received sensor data:"
            )
            print(data)


            allowed_fields = [

                "moisture",
                "temperature",
                "ph",
                "n",
                "p",
                "k"

            ]


            for field in allowed_fields:

                if field not in data:
                    continue


                value = data[field]


                if value is None:
                    continue


                try:

                    value = float(
                        value
                    )

                except:

                    continue


                latest_data[field] = value


            last_update_time = time.time()


            send_json(

                self,

                {

                    "status":
                        "ok",

                    "message":
                        "Sensor data received."

                }

            )


        except Exception as error:

            print(
                "POST error:",
                error
            )


            send_json(

                self,

                {

                    "status":
                        "error",

                    "message":
                        str(error)

                },

                400

            )


# ============================================================
# START SERVER
# ============================================================

server = HTTPServer(

    ("0.0.0.0", 8000),

    Handler

)


print()
print("==============================================")
print(" SMART CROP PROJECT")
print("==============================================")
print()
print("Open:")
print("http://localhost:8000")
print()
print("Server running on port 8000.")
print()
print("Waiting for ESP32 and market requests...")
print()


server.serve_forever()