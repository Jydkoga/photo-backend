from flask import Flask, jsonify, request
from flask_cors import CORS
import cloudinary
import cloudinary.uploader
import os
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
CORS(app)

# Configure Cloudinary using environment variables
cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
)


@app.route("/")
def index():
    return jsonify({"message": "Backend is running!"})


@app.route("/upload", methods=["POST"])
def upload_photo():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]

    # Upload to Cloudinary
    upload_result = cloudinary.uploader.upload(file)

    return jsonify(
        {"message": "Upload successful", "image_url": upload_result["secure_url"]}
    )
