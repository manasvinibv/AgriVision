from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import time
import os
import subprocess
import joblib
import pandas as pd

from urllib.parse import urlencode, urlparse, parse_qs
from datetime import datetime


# ============================================================
# DATA.GOV.IN API
# ============================================================

# PUT YOUR CURRENT WORKING / AUTHORIZED API KEY HERE
API_KEY = "579b464db66ec23bdd000001a45abb90b19d48db76e87f2a09caffb2"

API_URL = (
    "https://api.data.gov.in/resource/"
    "35985678-0d79-46b4-9ed6-6f13308a1d24"
)


# ============================================================
# MODEL FILES
# ============================================================

MARKET_MODEL_FILE = "market_price_model.pkl"
MARKET_FEATURES_FILE = "market_price_features.pkl"


# ============================================================
# LOAD MARKET PRICE MODEL
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

    print()
    print("WARNING")
    print("Market price model could not be loaded.")
    print(error)
    print()


# ============================================================
# SENSOR DATA
# ============================================================

# IMPORTANT:
# None means "no data".
# We do NOT use 0 as fake/default sensor data.

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
# SENSOR DATA VALIDATION
# ============================================================

def sensor_data_available():

    required = [
        "moisture",
        "ph",
        "n",
        "p",
        "k"
    ]

    for field in required:

        value = latest_data.get(field)

        if value is None:
            return False

        try:

            if float(value) <= 0:
                return False

        except:

            return False

    return True


# ============================================================
# CROP RECOMMENDATION
# ============================================================

def recommend(data):

    # We are NOT returning fake crops.
    #
    # Your crop_model.pkl is already present, but we have not
    # established its exact input feature structure in this
    # conversation.
    #
    # Therefore we do not invent a prediction.

    return []


# ============================================================
# DATA.GOV.IN MARKET API
# ============================================================

def get_market_data(
    crop,
    state,
    district
):

    # --------------------------------------------------------
    # DO NOT ALLOW EMPTY INPUT
    # --------------------------------------------------------

    if not crop or not state or not district:

        return {
            "status": "no_data",
            "message":
                "State, district and commodity are required."
        }

    # --------------------------------------------------------
    # API KEY CHECK
    # --------------------------------------------------------

    if (
        not API_KEY or
        API_KEY == "PUT_YOUR_WORKING_API_KEY_HERE"
    ):

        return {
            "status": "error",
            "message":
                "API key has not been configured in server.py."
        }

    print()
    print("==============================================")
    print("MARKET API REQUEST")
    print("==============================================")
    print("State    :", state)
    print("District :", district)
    print("Commodity:", crop)
    print()

    # --------------------------------------------------------
    # PARAMETERS
    # --------------------------------------------------------

    params = [
        ("api-key", API_KEY),
        ("format", "json"),
        ("limit", "100"),
        ("filters[State]", state),
        ("filters[District]", district),
        ("filters[Commodity]", crop)
    ]

    url = API_URL + "?" + urlencode(params)

    try:

        # ----------------------------------------------------
        # CURL
        # ----------------------------------------------------

        result = subprocess.run(
            [
                "curl",
                "-s",
                "--max-time",
                "60",
                url
            ],
            capture_output=True,
            text=True
        )

        # ----------------------------------------------------
        # CURL ERROR
        # ----------------------------------------------------

        if result.returncode != 0:

            print("CURL ERROR:")
            print(result.stderr)

            return {
                "status": "error",
                "message":
                    "Could not connect to data.gov.in."
            }

        raw_response = result.stdout.strip()

        if not raw_response:

            return {
                "status": "error",
                "message":
                    "data.gov.in returned an empty response."
            }

        # ----------------------------------------------------
        # JSON
        # ----------------------------------------------------

        try:

            data = json.loads(
                raw_response
            )

        except json.JSONDecodeError:

            print("Invalid API response:")
            print(raw_response[:1000])

            return {
                "status": "error",
                "message":
                    "data.gov.in did not return valid JSON."
            }

        # ----------------------------------------------------
        # API ERROR
        # ----------------------------------------------------

        if "error" in data:

            print(
                "DATA.GOV.IN ERROR:",
                data["error"]
            )

            return {
                "status": "error",
                "message":
                    data["error"]
            }

        # ----------------------------------------------------
        # RECORDS
        # ----------------------------------------------------

        records = data.get(
            "records",
            []
        )

        print(
            "Records received:",
            len(records)
        )

        if not records:

            return {
                "status": "no_data",
                "message":
                    "No market records found for the selected State, District and Commodity."
            }

        # ----------------------------------------------------
        # SORT RECORDS BY DATE
        # ----------------------------------------------------

        def get_date(record):

            date_text = record.get(
                "Arrival_Date"
            )

            if not date_text:
                return datetime.min

            try:

                return datetime.strptime(
                    date_text,
                    "%d/%m/%Y"
                )

            except:

                return datetime.min

        records.sort(
            key=get_date,
            reverse=True
        )

        # ----------------------------------------------------
        # LATEST VALID RECORD
        # ----------------------------------------------------

        latest = None

        for record in records:

            if record.get("Arrival_Date"):

                latest = record
                break

        if latest is None:

            return {
                "status": "no_data",
                "message":
                    "Market records were returned, but no valid arrival date was found."
            }

        # ----------------------------------------------------
        # REQUIRED PRICE FIELDS
        # ----------------------------------------------------

        min_price = pd.to_numeric(
            latest.get("Min_Price"),
            errors="coerce"
        )

        max_price = pd.to_numeric(
            latest.get("Max_Price"),
            errors="coerce"
        )

        modal_price = pd.to_numeric(
            latest.get("Modal_Price"),
            errors="coerce"
        )

        # We need valid price information.
        if (
            pd.isna(min_price) or
            pd.isna(max_price) or
            pd.isna(modal_price)
        ):

            return {
                "status": "no_data",
                "message":
                    "Latest market record does not contain valid price values."
            }

        # ----------------------------------------------------
        # RETURN ACTUAL MARKET RECORD
        # ----------------------------------------------------

        market_data = {

            "status": "ok",

            "date":
                latest.get(
                    "Arrival_Date"
                ),

            "commodity":
                latest.get(
                    "Commodity"
                ),

            "state":
                latest.get(
                    "State"
                ),

            "district":
                latest.get(
                    "District"
                ),

            "market":
                latest.get(
                    "Market"
                ),

            "variety":
                latest.get(
                    "Variety"
                ),

            "grade":
                latest.get(
                    "Grade"
                ),

            "min_price":
                float(min_price),

            "max_price":
                float(max_price),

            "modal_price":
                float(modal_price)
        }

        print()
        print("LATEST MARKET RECORD")
        print("--------------------")
        print(
            "Date:",
            market_data["date"]
        )
        print(
            "Commodity:",
            market_data["commodity"]
        )
        print(
            "Market:",
            market_data["market"]
        )
        print(
            "Modal price:",
            market_data["modal_price"]
        )

        return market_data

    except Exception as error:

        print()
        print("MARKET API ERROR:")
        print(error)

        return {
            "status": "error",
            "message": str(error)
        }


# ============================================================
# XGBOOST MARKET PRICE PREDICTION
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

    if not market_price_features:

        return {
            "status": "error",
            "message":
                "Market model feature file is not loaded."
        }

    try:

        # ----------------------------------------------------
        # READ ACTUAL MARKET DATA
        # ----------------------------------------------------

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

        min_price = pd.to_numeric(
            market_data.get(
                "min_price"
            ),
            errors="coerce"
        )

        max_price = pd.to_numeric(
            market_data.get(
                "max_price"
            ),
            errors="coerce"
        )

        # ----------------------------------------------------
        # REQUIRED VALUES
        # ----------------------------------------------------

        required_values = {
            "Arrival_Date": arrival_date,
            "Commodity": commodity,
            "District": district,
            "Market": market,
            "State": state,
            "Variety": variety,
            "Grade": grade
        }

        for name, value in required_values.items():

            if value is None or str(value).strip() == "":

                return {
                    "status": "no_data",
                    "message":
                        f"Missing required model input: {name}"
                }

        if pd.isna(min_price) or pd.isna(max_price):

            return {
                "status": "no_data",
                "message":
                    "Minimum or maximum market price is missing."
            }

        # ----------------------------------------------------
        # DATE
        # ----------------------------------------------------

        parsed_date = pd.to_datetime(
            arrival_date,
            dayfirst=True,
            errors="coerce"
        )

        if pd.isna(parsed_date):

            return {
                "status": "no_data",
                "message":
                    "Invalid market arrival date."
            }

        # ----------------------------------------------------
        # CREATE SAME FEATURES USED DURING TRAINING
        # ----------------------------------------------------

        row = pd.DataFrame([
            {

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

            }
        ])

        # ----------------------------------------------------
        # ONE HOT ENCODING
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # MATCH TRAINING FEATURES
        # ----------------------------------------------------

        row = row.reindex(
            columns=market_price_features,
            fill_value=0
        )

        row = row.fillna(0)

        # ----------------------------------------------------
        # PREDICT
        # ----------------------------------------------------

        prediction = market_price_model.predict(
            row
        )[0]

        prediction = float(
            prediction
        )

        # Never display a negative price.
        if prediction < 0:

            return {
                "status": "error",
                "message":
                    "Model returned an invalid negative price."
            }

        print()
        print(
            "XGBoost predicted modal price:",
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

        print()
        print("XGBOOST ERROR:")
        print(error)

        return {
            "status": "error",
            "message": str(error)
        }


# ============================================================
# SEND JSON RESPONSE
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

        # ----------------------------------------------------
        # HOME
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # CSS
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # IMAGES
        # ----------------------------------------------------

        elif path.startswith(
            "/images/"
        ):

            file_path = path.lstrip("/")

            if not os.path.exists(
                file_path
            ):

                self.send_error(
                    404
                )

                return

            if file_path.endswith(
                ".jpg"
            ):

                content_type = (
                    "image/jpeg"
                )

            elif file_path.endswith(
                ".png"
            ):

                content_type = (
                    "image/png"
                )

            else:

                self.send_error(
                    404
                )

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

        # ----------------------------------------------------
        # SENSOR DATA
        # ----------------------------------------------------

        elif path == "/data":

            if not sensor_data_available():

                send_json(
                    self,
                    {
                        "status": "no_data",
                        "message":
                            "Waiting for valid sensor data."
                    }
                )

                return

            response = {

                "status": "ok",

                "moisture":
                    latest_data[
                        "moisture"
                    ],

                "temperature":
                    latest_data[
                        "temperature"
                    ],

                "ph":
                    latest_data[
                        "ph"
                    ],

                "n":
                    latest_data[
                        "n"
                    ],

                "p":
                    latest_data[
                        "p"
                    ],

                "k":
                    latest_data[
                        "k"
                    ],

                "crops":
                    recommend(
                        latest_data
                    )
            }

            send_json(
                self,
                response
            )

        # ----------------------------------------------------
        # MARKET PRICE + XGBOOST
        # ----------------------------------------------------

        elif path == "/market-predict":

            # IMPORTANT:
            # There are NO default values.

            state = (
                query.get(
                    "state",
                    [""]
                )[0]
                .strip()
            )

            district = (
                query.get(
                    "district",
                    [""]
                )[0]
                .strip()
            )

            crop = (
                query.get(
                    "commodity",
                    [""]
                )[0]
                .strip()
            )

            # -----------------------------------------------
            # VALIDATE USER INPUT
            # -----------------------------------------------

            if (
                not state or
                not district or
                not crop
            ):

                send_json(
                    self,
                    {
                        "status": "no_data",
                        "message":
                            "Please enter State, District and Commodity."
                    }
                )

                return

            # -----------------------------------------------
            # GET ACTUAL API DATA
            # -----------------------------------------------

            market_data = get_market_data(
                crop,
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

            # -----------------------------------------------
            # XGBOOST
            # -----------------------------------------------

            prediction = (
                predict_market_price(
                    market_data
                )
            )

            response = {
                **market_data,
                "prediction":
                    prediction
            }

            send_json(
                self,
                response
            )

        # ----------------------------------------------------
        # UNKNOWN ROUTE
        # ----------------------------------------------------

        else:

            self.send_error(
                404
            )


    # ========================================================
    # POST
    # ========================================================

    def do_POST(self):

        global last_update_time

        # ----------------------------------------------------
        # ESP32 SENSOR UPDATE
        # ----------------------------------------------------

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
                        "status": "error",
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

            # ------------------------------------------------
            # ONLY UPDATE VALUES THAT ACTUALLY EXIST
            # ------------------------------------------------

            allowed_fields = [
                "moisture",
                "temperature",
                "ph",
                "n",
                "p",
                "k"
            ]

            for field in allowed_fields:

                if field in data:

                    value = data[field]

                    if value is None:
                        continue

                    try:

                        value = float(
                            value
                        )

                    except:

                        continue

                    latest_data[
                        field
                    ] = value

            last_update_time = (
                time.time()
            )

            send_json(
                self,
                {
                    "status": "ok",
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
                    "status": "error",
                    "message":
                        str(error)
                },
                400
            )


# ============================================================
# START ONE SERVER
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
print(
    "Open only:"
)
print(
    "http://localhost:8000"
)
print()
print(
    "One server is running on port 8000."
)
print()
print(
    "Waiting for ESP32 sensor data..."
)
print()

server.serve_forever()