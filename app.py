from flask import Flask, jsonify, request
from flask_cors import CORS
import cloudinary
import cloudinary.uploader
import os
from helper import extract_public_id
from dotenv import load_dotenv

from sqlalchemy import create_engine, Column, Integer, String, DateTime
from datetime import datetime
from sqlalchemy.orm import sessionmaker, declarative_base

load_dotenv()

app = Flask(__name__)
CORS(app)

# -------------------------
# Cloudinary Configuration
# -------------------------
cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
)

# -------------------------
# Database Setup
# -------------------------

DATABASE_URL = os.environ.get("DATABASE_URL")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()


class Photo(Base):
    __tablename__ = "photos"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, nullable=False)

    upload_time = Column(DateTime, default=datetime.utcnow)
    date = Column(String, nullable=True)
    title = Column(String, nullable=True)
    caption = Column(String, nullable=True)


# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

# -------------------------
# Routes
# -------------------------


@app.route("/")
def index():
    return jsonify({"message": "Backend is running!"})


@app.route("/upload", methods=["POST"])
def upload_photo():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]

    upload_result = cloudinary.uploader.upload(file, format="jpg")
    image_url = upload_result["secure_url"]

    # Save URL to database
    session = SessionLocal()
    title = request.form.get("title")
    caption = request.form.get("caption")
    date = request.form.get("date")

    new_photo = Photo(url=image_url, title=title, caption=caption, date=date)
    session.add(new_photo)
    session.commit()
    # Fetch updated list of photos
    photos = session.query(Photo).order_by(Photo.id.desc()).all()

    return jsonify(
        {
            "image_url": image_url,
            "photos": [
                {
                    "id": p.id,
                    "url": p.url,
                    "title": p.title,
                    "caption": p.caption,
                    "date": p.date,
                    "upload_time": p.upload_time.isoformat() if p.upload_time else None,
                }
                for p in photos
            ],
        }
    )


@app.route("/photos", methods=["GET"])
def get_photos():
    session = SessionLocal()
    photos = session.query(Photo).order_by(Photo.id.desc()).all()
    session.close()

    return jsonify(
        {
            "photos": [
                {
                    "id": p.id,
                    "url": p.url,
                    "title": p.title,
                    "caption": p.caption,
                    "date": p.date,
                    "upload_time": p.upload_time.isoformat() if p.upload_time else None,
                }
                for p in photos
            ]
        }
    )


@app.route("/photo/<int:photo_id>", methods=["DELETE"])
def delete_photo(photo_id):
    session = SessionLocal()
    photo = session.query(Photo).filter_by(id=photo_id).first()

    if not photo:
        session.close()
        return jsonify({"error": "Photo not found"}), 404

    public_id = extract_public_id(photo.url)

    # Delete from Cloudinary
    cloudinary.uploader.destroy(public_id)

    # Delete from DB
    session.delete(photo)
    session.commit()
    session.close()

    return jsonify({"message": "Photo deleted"})


# -------------------------
# Debug Routes
# -------------------------
@app.route("/debug/photos", methods=["GET"])
def debug_photos():
    session = SessionLocal()
    count = session.query(Photo).count()
    session.close()
    return jsonify({"count": count})
