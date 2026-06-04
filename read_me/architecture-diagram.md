# Implemented System Architecture

This document describes the high-level system architecture, component layout, network boundaries, and security relationships of the PaperlessBoss backend application.

---

## 🏗️ System Architecture Diagram

The diagram below visualizes the client request path, Docker container orchestration boundaries, internal FastAPI modules, and external third-party cloud integrations:

```mermaid
graph TD
    %% Styling
    classDef client fill:#e3f2fd,stroke:#1e88e5,stroke-width:2px;
    classDef proxy fill:#ede7f6,stroke:#5e35b1,stroke-width:2px;
    classDef app fill:#f1f8e9,stroke:#7cb342,stroke-width:2px;
    classDef db fill:#ffebee,stroke:#e53935,stroke-width:2px;
    classDef ext fill:#fffde7,stroke:#fdd835,stroke-width:2px;
    
    %% Nodes
    Client[Web Browser / Postman / Mobile App]:::client
    
    subgraph Docker Container Environment [Docker Compose Network]
        Nginx[Nginx Reverse Proxy<br/>Ports: 80 / 443 / SSL]:::proxy
        Uvicorn[Uvicorn ASGI Server<br/>Port: 8000 (Internal)]:::proxy
        
        subgraph FastAPI Backend Application [python codebase]
            Routes[API Routing Layer<br/>api/v1/auth, api/v1/profile, /validate-excel]:::app
            Middleware[CORS & Cookie Middleware]:::app
            Services[Services Layer<br/>auth_service, profile_service, email]:::app
            ExcelEngine[Excel Validation Engine<br/>validator, rules, utils]:::app
            Models[SQLAlchemy 2.0 ORM Models<br/>User, Company, Signatory, OTP, RefreshToken]:::app
            DBConn[Database Session Pooler<br/>Asyncpg Connection Pool]:::app
        end
    end
    
    subgraph Cloud Infrastructure [External Services]
        SupabaseDB[(Supabase Cloud PostgreSQL<br/>Port: 5432 / pooler.supabase.com)]:::db
        SupabaseStorage[(Supabase Storage<br/>Private Bucket / REST API)]:::db
        SMTPServer[GoDaddy SMTP Server<br/>smtpout.secureserver.net:465 / SSL]:::ext
    end
    
    %% Relationships
    Client -- HTTPS / SSL --> Nginx
    Nginx -- Proxy Pass (Port 8000) --> Uvicorn
    Uvicorn --> Middleware
    Middleware --> Routes
    
    Routes -- Call Logic --> Services
    Routes -- Parse Upload --> ExcelEngine
    
    Services -- Query / Mutate --> Models
    Services -- Send Email --> SMTPServer
    
    ExcelEngine -- Push valid .xlsx --> SupabaseStorage
    ExcelEngine -- Fetch Signed URL --> SupabaseStorage
    
    Models --> DBConn
    DBConn -- SSL Connection --> SupabaseDB
```

---

## 📦 Component Roles & Tech Stack

### 1. Ingress & Routing (Nginx)
* **Role**: Handles SSL/TLS termination, routes traffic, blocks non-API request patterns, and acts as the entrypoint to the bridge network.
* **Ports**: `80` (redirects to `443` HTTPS), `443` (public proxying).
* **Certificate Store**: Standard Certbot Cert directory (`/etc/letsencrypt/live/paperlessboss.com/`) mounted directly from the host.

### 2. ASGI Application Server (Uvicorn / FastAPI)
* **Role**: Asynchronous ASGI server running the FastAPI app.
* **Security Controls**:
  * CORS middleware restricting access to verified company origins (`https://paperlessboss.com`, `http://localhost:3000`, etc.).
  * Automatic documentation toggle (Swagger UI `/docs` is hidden automatically in production).

### 3. Business Services (FastAPI Modules)
* **Auth Service**:
  * Performs bcrypt password hashing.
  * Manages OTP lifecycle (creates hashes, registers attempts, blocks registrations during cooldown).
  * Validates access JWTs (15 min lifespan) and refresh tokens (7 days database-backed HttpOnly cookie).
* **Profile Service**:
  * Implements tenant isolation checks (validates GSTIN and CIN uniqueness to prevent hijacked company claims).
  * Performs model mapping (linking users, companies, and signatories).
* **Excel Engine**:
  * Reads multipart form-data Excel streams.
  * Validates rows column-by-column using Pydantic regex/date rules.
  * Converts float artifacts and leading zero drops.

### 4. Database & Storage Layer (Supabase & PostgreSQL)
* **Connection Manager**:
  * Manages an asynchronous connection pool using `asyncpg` and SQLAlchemy 2.0 with a connection recycler (`pool_recycle=1800`) and pre-pings.
  * Connects over SSL (cert validation is bypassed for flexible docker host-routing).
* **PostgreSQL DB**:
  * Stores application schemas.
  * Employs btree indexes on performance-critical columns (`users.email`, `companies.gstin`, `companies.cin`, `companies.pan`, `refresh_tokens.user_id`, `refresh_tokens.token`).
* **Supabase Storage**:
  * Private object storage bucket (`appointment_excel_files`). Validated Excel uploads are saved here under UUID names.
  * Returns secure signed URLs (expired in 15 minutes) instead of public endpoints.

---

## 🔒 Implemented Security Boundaries

> [!NOTE]
> * **XSS Shielding**: The refresh token is stored in an `HttpOnly`, `Secure` (production), `SameSite=Lax` cookie, meaning JavaScript on the frontend cannot read or steal it.
> * **CSRF Mitigation**: Short-lived (15 minutes) Access Tokens are passed via the standard `Authorization: Bearer` header, keeping requests resilient to cookie-based CSRF attacks.
> * **Brute Force Lockout**: OTP verification table tracks attempts and locks verification rows permanently after 5 failures.
> * **Network Isolation**: The backend FastAPI container does not expose any ports directly to the host system in production; it is only reachable via Nginx on the internal Docker network.
