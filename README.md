# PaperlessBoss Backend API

A secure, high-performance, asynchronous user authentication and email OTP verification system built using **FastAPI** and **SQLAlchemy 2.0** connected to Supabase PostgreSQL.

---

## 🌟 Core Features

1. **FastAPI Web Server**: Blazing fast, asynchronous execution featuring out-of-the-box self-documenting OpenAPI specifications (`/docs`).
2. **Native Cryptographic Password Hashing**: Leverages standard `bcrypt` directly to securely generate and verify passwords, avoiding legacy wrapper bottlenecks.
3. **High-Security Database-Backed OTPs**: Implements **cryptographic hashing (`hashed_otp` with SHA-256)** for 6-digit verification codes in the database, ensuring zero plaintext exposure in case of data breaches.
4. **Dynamic SMTP Mail Dispatch**: Integrated with `aiosmtplib` to automatically upgrade to secure connections (**STARTTLS on port 587** or **direct TLS on port 465**). Fully optimized for Gmail App Passwords out-of-the-box.
5. **Robust Registration Retry Flow**: Gracefully allows unverified users (`is_verified = False`) to submit registrations again. This automatically updates their password, invalidates previous codes, and dispatches a fresh verification OTP.
6. **Indian Standard Time (IST) Time-tracking**: Configured to log all account creations, updates, and OTP expirations under naive local **IST (UTC+05:30)** timestamps.

---

## 📂 Project Architecture

```text
paperlessboss-be/
│
├── .env                  # Secrets and configuration parameters
├── main.py               # Application entry point, lifespan, CORS, and schema syncer
├── requirements.txt      # Python dependencies
├── postman_collection.json # Import-ready Postman collection for all routes
│
├── db/
│   ├── db_connection.py  # Asynchronous connection pooling and session factory
│   └── models.py         # SQLAlchemy models (User, OTPVerification)
│
├── core/
│   ├── config.py         # Settings loader using Pydantic Settings with Gmail fallback
│   └── security.py       # Hashing functions (bcrypt) and JWT encode/decode
│
├── schemas/
│   └── auth.py           # Pydantic validation schemas (UserRegister, VerifyOTP, Token)
│
├── services/
│   ├── auth_service.py   # Auth operations (Register, Login, OTP verify/resend)
│   └── email.py          # SMTP email builder and async transmitter
│
├── api/
│   ├── deps.py           # Database session dependency injection
│   └── v1/
│       └── auth.py       # Auth endpoints (register, verify-otp, resend-otp, login, me)
│
└── tmp/
    └── test_auth_flow.py # Self-bootstrapping end-to-end integration test flow
```

---

## ⚙️ Setup & Installation

### 1. Configure `.env` File
Create or update your `.env` file at the root of the project with your Supabase PostgreSQL credentials and Gmail SMTP App Password:
```env
DB_HOST = db.skzceavurcikyajjtpar.supabase.co
DB_PORT = 6543
DB_NAME = postgres
DB_USER = postgres
DB_PASS = PaperLessBoss2026

EMAILS_FROM_EMAIL = your-gmail-address@gmail.com
EMAIL_PASS = your-16-char-app-password
```

### 2. Install Dependencies
Activate your virtual environment and install the required modules:
```bash
.\venv\Scripts\pip install fastapi uvicorn "pydantic[email]" pydantic-settings bcrypt pyjwt cryptography aiosmtplib asyncpg SQLAlchemy
```

### 3. Run the Server
Launch the development server:
```bash
.\venv\Scripts\uvicorn main:app --reload
```
*Note: The application features an automatic lifespan hook that will automatically synchronize and build the necessary tables in your database upon startup.*

---

## 📡 API Reference & Flow

All endpoints are prefixed with `/api/v1/auth`.

### 1. Register User
* **Endpoint**: `POST /register`
* **Payload**:
  ```json
  {
    "email": "user@example.com",
    "password": "SecurePassword123!"
  }
  ```
* **Process**: Checks if user exists. If they exist but are not verified, it updates their password and sends a new OTP. Otherwise, it creates a new user, hashes their password, generates a cryptographically random 6-digit OTP, saves the SHA-256 hash of the OTP to the DB, and dispatches the plaintext code in a styled HTML template to the recipient's mailbox.

### 2. Verify Email OTP
* **Endpoint**: `POST /verify-otp`
* **Payload**:
  ```json
  {
    "email": "user@example.com",
    "otp_code": "123456"
  }
  ```
* **Process**: Hashes the incoming OTP and validates it against the active, unexpired, unused database records. On successful match, it unlocks the user account by setting `is_verified = True`.

### 3. Resend Verification OTP
* **Endpoint**: `POST /resend-otp`
* **Payload**:
  ```json
  {
    "email": "user@example.com"
  }
  ```
* **Process**: Invalidates all pending older OTP entries and dispatches a fresh verification code to the recipient.

### 4. User Login
* **Endpoint**: `POST /login`
* **Payload**:
  ```json
  {
    "email": "user@example.com",
    "password": "SecurePassword123!"
  }
  ```
* **Process**: Verifies email, password match, and verified status (`is_verified == True`). On success, generates and returns a secure JWT access token.

### 5. Get Profile
* **Endpoint**: `GET /me`
* **Headers**: `Authorization: Bearer <your_jwt_token>`
* **Process**: Decodes the JWT session token, fetches the associated user profile from the database, and returns the profile details safely.

---

## 🧪 Postman & Verification

We have prepared a ready-to-import Postman Collection file at **`postman_collection.json`** in your project root:
1. Open Postman and click **Import**.
2. Drag and drop the **`postman_collection.json`** file.
3. Once imported, you can run through **Register**, check your email for the OTP code, execute **Verify Email OTP**, and then run **User Login**.
4. The login request features a built-in Postman test script that automatically extracts and saves the returned access token into the dynamic `{{access_token}}` collection variable, immediately authorizing the secure `Get Profile (Me)` endpoint!

---

## 🐳 Docker Deployment

You can deploy and run the entire application using Docker or Docker Compose. 

### Method 1: Using Docker Compose (Recommended)
This builds the image, passes the `.env` settings automatically, maps ports, and starts the container:
```bash
# Build and start the container in the background
docker-compose up --build -d

# Check live container logs
docker-compose logs -f
```

### Method 2: Using Raw Docker
If you prefer running raw Docker commands:
```bash
# 1. Build the Docker image from the root directory context
docker build -t paperlessboss-be -f backend_api/Dockerfile .

# 2. Run the container, binding your .env file and exposing port 8000
docker run -d --name paperlessboss_api -p 8000:8000 --env-file .env paperlessboss-be
```

