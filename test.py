from flask import Flask, request
import json

app = Flask(__name__)
@app.post("/alerts")
def alerts():
    print(json.dumps(request.json, indent=2))
    return "OK\n"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9000)