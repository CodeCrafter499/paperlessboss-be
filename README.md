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

For a visual diagram and in-depth description of the container layout, database connections, and security boundaries:
👉 **[Detailed Architecture Walkthrough](file:///d:/peperless_be/paperlessboss-be/read_me/architecture-diagram.md)**

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

## 📡 API Reference & Detailed Documentation

For a complete, interactive, and detailed guide explaining each API endpoint, request payloads, response structures, sequence flows, and concrete `curl` examples, please read:
👉 **[Detailed API Documentation Manual](file:///d:/peperless_be/paperlessboss-be/read_me/api-documentation.md)**

For a complete breakdown of the statutory employee records Excel validation engine, exact column headers, formatting tips, and error configurations, please read:
👉 **[Excel Validation Documentation](file:///d:/peperless_be/paperlessboss-be/read_me/excel-validation.md)**

---

## 🧪 Postman & Verification

We have prepared ready-to-import Postman Collections in the project repository under:
* 📥 **Local API Collection**: [postman_collection_local.json](file:///d:/peperless_be/paperlessboss-be/postman_coll/postman_collection_local.json)
* 📥 **Production API Collection**: [postman_collection_production.json](file:///d:/peperless_be/paperlessboss-be/postman_coll/postman_collection_production.json)

### Quick Start with Postman:
1. Open Postman and click **Import**.
2. Select either **`postman_collection_local.json`** or **`postman_collection_production.json`**.
3. Once imported, you can run through **Register**, check your email/logs for the OTP, run **Verify Email OTP**, and then **User Login**.
4. The **User Login** request features a built-in Postman test script that automatically extracts and saves the returned access token into the dynamic `{{access_token}}` collection variable, immediately authorizing the secure `Get Profile (Me)`, Company Profile, and Authorised Signatory endpoints!


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

---

### 🛡️ Production Deployment (Nginx Reverse Proxy & HTTPS/SSL)

For live production hosting under **`https://paperlessboss.com`**, we have containerized a secure, production-grade Nginx reverse proxy that isolates the FastAPI service on a private Docker bridge network and terminates SSL automatically.

#### 1. Install Docker and Docker Compose on Your Ubuntu Server
If Docker is not yet installed on your server, run the following setup commands:
```bash
# Update and install dependencies
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

# Add Docker GPG key
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Setup non-root execution (recommended)
sudo usermod -aG docker $USER
newgrp docker
```

#### 2. Obtain Let's Encrypt SSL/TLS Certificates on Host
The Nginx container is preconfigured to load certificates from the standard host path `/etc/letsencrypt/live/paperlessboss.com/`. Generate them using Certbot standalone:
```bash
sudo apt install certbot -y
sudo certbot certonly --standalone -d paperlessboss.com -d www.paperlessboss.com
```

#### 3. Configure Production Secrets
Create or update your `.env` file at the root of the project with your production Supabase database pooler credentials and set the environment to `production`:
```env
DB_HOST = aws-1-ap-northeast-2.pooler.supabase.com
DB_PORT = 5432
DB_NAME = postgres
DB_USER = postgres.skzceavurcikyajjtpar
DB_PASS = your-database-password

EMAILS_FROM_EMAIL = your-email@gmail.com
EMAIL_PASS = your-smtp-app-password

# CRITICAL: This hides interactive /docs (Swagger) automatically in production
ENVIRONMENT = production
```

#### 4. Stop Host-Level Web Servers
To deploy a completely isolated, unified, and self-contained Docker environment that serves **both your static frontend and backend APIs** on ports `80` and `443` in one place:

1. Stop and disable the native host-level Nginx to free up ports `80` and `443`:
   ```bash
   sudo systemctl stop nginx
   sudo systemctl disable nginx
   ```
2. The Docker Compose configuration is set up to **automatically mount** your server's static frontend files directly from `/var/www/html` into the container, rendering them instantly.

#### 5. Deploy the Stack
Spin up the entire unified environment:
```bash
docker compose -f docker-compose.prod.yml up --build -d
```
```bash
# Check container status
docker compose -f docker-compose.prod.yml ps

# View real-time web server logs
docker compose -f docker-compose.prod.yml logs -f nginx
```


