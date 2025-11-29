from flask import Flask, jsonify, request, g
from flask_cors import CORS
import cloudinary
import cloudinary.uploader
import os
from helper import extract_public_id
from dotenv import load_dotenv

from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base

import functools

load_dotenv()

app = Flask(__name__)
CORS(app)

app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "dev-secret-change-me")

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


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Photo(Base):
    __tablename__ = "photos"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, nullable=False)

    upload_time = Column(DateTime, default=datetime.utcnow)
    date = Column(String, nullable=True)
    title = Column(String, nullable=True)
    caption = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)


# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

# -------------------------
# JWT helpers
# -------------------------


def create_access_token(user_id):
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(days=7),
    }
    token = jwt.encode(payload, app.config["JWT_SECRET_KEY"], algorithm="HS256")
    # PyJWT >= 2 returns a string already
    return token


def decode_access_token(token):
    try:
        payload = jwt.decode(token, app.config["JWT_SECRET_KEY"], algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def login_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Authorization header missing or invalid"}), 401

        token = auth_header.split(" ", 1)[1]
        payload = decode_access_token(token)
        if not payload:
            return jsonify({"error": "Invalid or expired token"}), 401

        g.current_user_id = payload.get("user_id")
        if g.current_user_id is None:
            return jsonify({"error": "Invalid token payload"}), 401

        return f(*args, **kwargs)

    return wrapper


# -------------------------
# Routes
# -------------------------


@app.route("/")
def index():
    return jsonify({"message": "Backend is running!"})


@app.route("/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    session = SessionLocal()
    existing = session.query(User).filter_by(username=username).first()
    if existing:
        session.close()
        return jsonify({"error": "Username already exists"}), 400

    password_hash = generate_password_hash(password)
    user = User(username=username, password_hash=password_hash)
    session.add(user)
    session.commit()
    session.close()

    return jsonify({"message": "User registered successfully"})


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    session = SessionLocal()
    user = session.query(User).filter_by(username=username).first()

    if not user or not check_password_hash(user.password_hash, password):
        session.close()
        return jsonify({"error": "Invalid credentials"}), 401

    token = create_access_token(user.id)
    session.close()
    return jsonify({"access_token": token})


@app.route("/me", methods=["GET"])
@login_required
def me():
    session = SessionLocal()
    user = session.query(User).filter_by(id=g.current_user_id).first()
    if not user:
        session.close()
        return jsonify({"error": "User not found"}), 404

    data = {
        "id": user.id,
        "username": user.username,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
    session.close()
    return jsonify(data)


@app.route("/upload", methods=["POST"])
@login_required
def upload_photo():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]

    upload_result = cloudinary.uploader.upload(file, format="jpg")
    image_url = upload_result["secure_url"]

    # Save URL to database
    session = SessionLocal()
    user_id = g.current_user_id
    title = request.form.get("title")
    caption = request.form.get("caption")
    date = request.form.get("date")

    new_photo = Photo(
        url=image_url, title=title, caption=caption, date=date, user_id=user_id
    )
    session.add(new_photo)
    session.commit()
    # Fetch updated list of photos
    photos = (
        session.query(Photo).filter_by(user_id=user_id).order_by(Photo.id.desc()).all()
    )

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
@login_required
def get_photos():
    session = SessionLocal()
    user_id = g.current_user_id
    photos = (
        session.query(Photo).filter_by(user_id=user_id).order_by(Photo.id.desc()).all()
    )
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
@login_required
def delete_photo(photo_id):
    session = SessionLocal()
    user_id = g.current_user_id
    photo = session.query(Photo).filter_by(id=photo_id, user_id=user_id).first()

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


# -------------------------
# Debug Metadata Route
# -------------------------
@app.route("/debug/metadata", methods=["GET"])
def debug_metadata():
    session = SessionLocal()
    photos = session.query(Photo).order_by(Photo.id.asc()).all()

    data = [
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

    session.close()
    return jsonify({"photos": data})
