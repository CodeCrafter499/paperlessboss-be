# PaperlessBoss API Documentation Manual

This manual provides a detailed technical reference for all backend APIs in PaperlessBoss. It covers authentication flows, session management, profile setups, security controls, error conditions, and concrete integration examples.

---

## 🛠️ Global API Configuration

* **Local Base URL**: `http://localhost:8000`
* **Production Base URL**: `https://paperlessboss.com`
* **API Prefix**: All core endpoints are versioned and structured under `/api/v1`.
* **Content Type**: Content bodies must use `application/json` (except for Excel validation which uses `multipart/form-data`).

---

## 🔄 Sequence Diagram: Authentication & Token Rotation

Below is a sequence diagram showcasing the onboarding, secure login with cookies, and refresh token rotation:

```mermaid
sequenceDiagram
    autonumber
    actor Client as Client / Frontend
    participant API as FastAPI Backend
    participant DB as Supabase PostgreSQL
    participant SMTP as SMTP Relay (Secureserver)

    Note over Client, SMTP: Phase 1: Onboarding
    Client->>API: POST /api/v1/auth/register (email, password)
    API->>DB: Check existing users
    API->>DB: Create user (is_verified = False) & store hashed OTP
    API->>SMTP: Dispatch plaintext OTP (Background Task)
    SMTP-->>Client: Receive email verification code (6 digits)
    API-->>Client: 201 Created (UserOut with IST created_at)
    Client->>API: POST /api/v1/auth/verify-otp (email, otp_code)
    API->>DB: Check attempts limit & verify hashed OTP
    API->>DB: Set is_verified = True
    API-->>Client: 200 OK (OTP verified successfully)

    Note over Client, SMTP: Phase 2: Secure Session Start
    Client->>API: POST /api/v1/auth/login (email, password)
    API->>DB: Verify password & is_verified
    API->>API: Generate 15-minute JWT Access Token
    API->>API: Generate 7-day Refresh Token
    API->>DB: Store hashed Refresh Token
    API-->>Client: 200 OK (Access Token JSON + HttpOnly cookie "refresh_token")

    Note over Client, SMTP: Phase 3: Token Rotation (Automatic Refresh)
    Client->>API: GET /api/v1/auth/me (Auth: Bearer access_token)
    API-->>Client: 200 OK (User profile details)
    Note over Client: Access Token expires (15 mins)
    Client->>API: POST /api/v1/auth/refresh (Cookie: refresh_token)
    API->>DB: Validate cookie refresh token (Reuse check!)
    API->>DB: Revoke old refresh token & generate new pair
    API-->>Client: 200 OK (New Access Token JSON + New HttpOnly cookie "refresh_token")

    Note over Client, SMTP: Phase 4: Sign-out
    Client->>API: POST /api/v1/auth/logout
    API->>DB: Revoke/delete active refresh token in database
    API-->>Client: 200 OK (Cookie "refresh_token" cleared)
```

---

## 🛡️ Security Safeguards & Rules

> [!IMPORTANT]
> The backend implements several security controls to prevent brute forcing, session hijacking, and database pollution:

1. **OTP Cooldown Timer**: 
   * A minimum wait time of **60 seconds** is enforced between registering or requesting an OTP resend for the same email address.
   * Attempting to request codes faster yields a `429 Too Many Requests` error.
2. **OTP Attempts Lockout**:
   * Each OTP entry allows a maximum of **5 failed verification attempts**.
   * Upon reaching the 5th failed attempt, the verification entry is permanently invalidated. The user must request a new OTP to proceed.
3. **HttpOnly Refresh Cookies**:
   * Refresh tokens are served with attributes: `HttpOnly=True`, `Secure=True` (in production), and `SameSite=Lax`. This shields them from Cross-Site Scripting (XSS) access.
   * Access tokens expire in **15 minutes**, forcing the client to silently rotate them using the `/refresh` endpoint.
4. **Tenant Isolation / Hijack Protection**:
   * Users cannot associate themselves with a Company if its **GSTIN** or **CIN** has already been claimed by another registered user.
   * Any hijack attempt results in a `400 Bad Request`.
5. **Signed Storage URLs**:
   * Excel files are saved in a private Supabase bucket (`appointment_excel_files`). 
   * Instead of public URLs, the system issues a secure **signed URL valid for 15 minutes**.

---

## 📡 Endpoint Catalog

### 1. Registration & Verification

#### Register User
* **Method**: `POST`
* **Path**: `/api/v1/auth/register`
* **Auth**: None (Public)
* **Request Body**:
  | Field | Type | Description |
  | :--- | :--- | :--- |
  | `email` | String (EmailStr) | Valid email address. |
  | `password` | String | Must be at least 8 characters long. |
* **Request JSON Example**:
  ```json
  {
    "email": "developer@example.com",
    "password": "SecurePassword123!"
  }
  ```
* **Success Response (201 Created)**:
  ```json
  {
    "id": "c6c27fc7-73fc-4cdd-8864-954a9c4d760c",
    "email": "developer@example.com",
    "is_active": true,
    "is_verified": false,
    "created_at": "2026-06-04T06:08:15.917717+05:30"
  }
  ```
* **Error Responses**:
  * `400 Bad Request` if email is already registered and verified.
  * `429 Too Many Requests` if within the 60-second OTP cooldown.
* **Curl Example**:
  ```bash
  curl -X POST http://localhost:8000/api/v1/auth/register \
       -H "Content-Type: application/json" \
       -d '{"email": "developer@example.com", "password": "SecurePassword123!"}'
  ```

---

#### Verify OTP
* **Method**: `POST`
* **Path**: `/api/v1/auth/verify-otp`
* **Auth**: None (Public)
* **Request Body**:
  | Field | Type | Description |
  | :--- | :--- | :--- |
  | `email` | String (EmailStr) | The email associated with the registration. |
  | `otp_code` | String | Exactly 6 numeric digits. |
* **Request JSON Example**:
  ```json
  {
    "email": "developer@example.com",
    "otp_code": "481516"
  }
  ```
* **Success Response (200 OK)**:
  ```json
  {
    "message": "OTP verified successfully. Your account is now active."
  }
  ```
* **Error Responses**:
  * `400 Bad Request` if the OTP is invalid, expired, or the user is already verified.
  * `400 Bad Request` if locked out due to exceeding 5 attempts (requiring a new resend).
* **Curl Example**:
  ```bash
  curl -X POST http://localhost:8000/api/v1/auth/verify-otp \
       -H "Content-Type: application/json" \
       -d '{"email": "developer@example.com", "otp_code": "481516"}'
  ```

---

#### Resend OTP
* **Method**: `POST`
* **Path**: `/api/v1/auth/resend-otp`
* **Auth**: None (Public)
* **Request Body**:
  | Field | Type | Description |
  | :--- | :--- | :--- |
  | `email` | String (EmailStr) | Target email. |
* **Request JSON Example**:
  ```json
  {
    "email": "developer@example.com"
  }
  ```
* **Success Response (200 OK)**:
  ```json
  {
    "message": "A new verification code has been dispatched to your mailbox."
  }
  ```
* **Error Responses**:
  * `404 Not Found` if the email has no pending/unverified user registration.
  * `429 Too Many Requests` if within the 60-second cooldown from the last request.
* **Curl Example**:
  ```bash
  curl -X POST http://localhost:8000/api/v1/auth/resend-otp \
       -H "Content-Type: application/json" \
       -d '{"email": "developer@example.com"}'
  ```

---

### 2. Session Management

#### User Login
* **Method**: `POST`
* **Path**: `/api/v1/auth/login`
* **Auth**: None (Public)
* **Request Body**:
  | Field | Type | Description |
  | :--- | :--- | :--- |
  | `email` | String (EmailStr) | Registered email address. |
  | `password` | String | Password. |
* **Success Response (200 OK)**:
  * Returns access token in JSON body.
  * Sets `refresh_token` as an HttpOnly, secure cookie on the response.
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer"
  }
  ```
* **Error Responses**:
  * `400 Bad Request` if the user is registered but has not yet completed OTP verification.
  * `401 Unauthorized` if invalid email or password credentials.
* **Curl Example**:
  ```bash
  curl -X POST http://localhost:8000/api/v1/auth/login \
       -H "Content-Type: application/json" \
       -d '{"email": "developer@example.com", "password": "SecurePassword123!"}'
  ```

---

#### Refresh Token Rotation
* **Method**: `POST`
* **Path**: `/api/v1/auth/refresh`
* **Auth**: Cookie-based (`refresh_token` must be present in the cookies).
* **Success Response (200 OK)**:
  * Rotates the refresh token (stores a new one in cookies and revokes/deletes the old one).
  * Returns a new access token valid for 15 minutes.
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer"
  }
  ```
* **Error Responses**:
  * `401 Unauthorized` if no cookie is sent or if the refresh token is invalid or expired.
* **Curl Example**:
  ```bash
  curl -X POST http://localhost:8000/api/v1/auth/refresh \
       -b "refresh_token=your_refresh_token_cookie_value"
  ```

---

#### User Logout
* **Method**: `POST`
* **Path**: `/api/v1/auth/logout`
* **Auth**: Cookie-based.
* **Success Response (200 OK)**:
  * Deletes the session token from the DB.
  * Clears the `refresh_token` cookie by setting it with max-age 0.
  ```json
  {
    "message": "Logged out successfully"
  }
  ```
* **Curl Example**:
  ```bash
  curl -X POST http://localhost:8000/api/v1/auth/logout \
       -b "refresh_token=your_refresh_token_cookie_value"
  ```

---

#### Get Session Profile (Me)
* **Method**: `GET`
* **Path**: `/api/v1/auth/me`
* **Auth**: Bearer Authorization (`Authorization: Bearer <access_token>`).
* **Success Response (200 OK)**:
  ```json
  {
    "id": "c6c27fc7-73fc-4cdd-8864-954a9c4d760c",
    "email": "developer@example.com",
    "is_active": true,
    "is_verified": true,
    "created_at": "2026-06-04T06:08:15.917717+05:30"
  }
  ```
* **Curl Example**:
  ```bash
  curl -X GET http://localhost:8000/api/v1/auth/me \
       -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  ```

---

### 3. Profiles & Tenants

#### Get Company Profile
* **Method**: `GET`
* **Path**: `/api/v1/profile/company`
* **Auth**: Bearer Authorization.
* **Success Response (200 OK)**:
  ```json
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Acme Technologies Ltd",
    "address": "101, Tech Park, Sector 5, Bangalore",
    "gstin": "37ABCDE1234F1ZK",
    "pan": "ABCDE1234F",
    "cin": "L17110MH1973PLC019786",
    "labour_identification_number": "LABOUR998877",
    "email": "corporate@acme.com",
    "mobile_no": "9876543210",
    "created_at": "2026-06-04T06:12:00.000000+05:30",
    "updated_at": "2026-06-04T06:12:00.000000+05:30"
  }
  ```
* **Error Responses**:
  * `404 Not Found` if no company profile is linked to the active user.
* **Curl Example**:
  ```bash
  curl -X GET http://localhost:8000/api/v1/profile/company \
       -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  ```

---

#### Create or Update Company Profile
* **Method**: `POST`
* **Path**: `/api/v1/profile/company`
* **Auth**: Bearer Authorization.
* **Request Body**:
  | Field | Type | Required | Description / Validations |
  | :--- | :--- | :--- | :--- |
  | `name` | String | Yes | Min length 1. |
  | `address` | String | No | Max length 1000. |
  | `gstin` | String | No | Must match the standard 15-character Indian GSTIN format. |
  | `pan` | String | No | Must match standard 10-character Indian PAN format. |
  | `cin` | String | No | Must match 21-character CIN format. |
  | `labour_identification_number` | String | No | Max length 255. |
  | `email` | String | No | Valid email format. |
  | `mobile_no` | String | No | Max length 20. |

> [!NOTE]
> **Key Business Logic**:
> 1. **Auto PAN Extraction**: If `gstin` is provided but `pan` is left blank, the backend automatically extracts characters 3 to 12 from the GSTIN and sets it as the PAN.
> 2. **Integrity Validation**: If both are provided, characters 3 to 12 of the GSTIN **must match** the PAN. Otherwise, a `422 Unprocessable Entity` is returned.
> 3. **Hijack Protection**: If another tenant has already registered a profile with the same GSTIN or CIN, the system blocks registration with `400 Bad Request`.

* **Request JSON Example**:
  ```json
  {
    "name": "Acme Technologies Ltd",
    "address": "101, Tech Park, Sector 5, Bangalore",
    "gstin": "37ABCDE1234F1ZK",
    "cin": "L17110MH1973PLC019786",
    "labour_identification_number": "LABOUR998877",
    "email": "corporate@acme.com",
    "mobile_no": "9876543210"
  }
  ```
* **Success Response (200 OK)**:
  ```json
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "Acme Technologies Ltd",
    "address": "101, Tech Park, Sector 5, Bangalore",
    "gstin": "37ABCDE1234F1ZK",
    "pan": "ABCDE1234F",
    "cin": "L17110MH1973PLC019786",
    "labour_identification_number": "LABOUR998877",
    "email": "corporate@acme.com",
    "mobile_no": "9876543210",
    "created_at": "2026-06-04T06:12:00.000000+05:30",
    "updated_at": "2026-06-04T06:15:30.000000+05:30"
  }
  ```
* **Curl Example**:
  ```bash
  curl -X POST http://localhost:8000/api/v1/profile/company \
       -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
       -H "Content-Type: application/json" \
       -d '{"name": "Acme Technologies Ltd", "gstin": "37ABCDE1234F1ZK"}'
  ```

---

#### Get Authorised Signatory Profile
* **Method**: `GET`
* **Path**: `/api/v1/profile/signatory`
* **Auth**: Bearer Authorization.
* **Success Response (200 OK)**:
  ```json
  {
    "id": "6a0e8400-e29b-41d4-a716-446655440111",
    "user_id": "c6c27fc7-73fc-4cdd-8864-954a9c4d760c",
    "name": "John Doe",
    "address": "Flat 4B, Emerald Crest, Bangalore",
    "pan": "XYZAB1234C",
    "email": "john.doe@acme.com",
    "mobile_no": "9876543211",
    "created_at": "2026-06-04T06:13:00.000000+05:30",
    "updated_at": "2026-06-04T06:13:00.000000+05:30"
  }
  ```
* **Error Responses**:
  * `404 Not Found` if no signatory profile exists for the active user.
* **Curl Example**:
  ```bash
  curl -X GET http://localhost:8000/api/v1/profile/signatory \
       -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  ```

---

#### Create or Update Authorised Signatory Profile
* **Method**: `POST`
* **Path**: `/api/v1/profile/signatory`
* **Auth**: Bearer Authorization.
* **Request Body**:
  | Field | Type | Required | Description / Validations |
  | :--- | :--- | :--- | :--- |
  | `name` | String | Yes | Min length 1. |
  | `address` | String | No | Max length 1000. |
  | `pan` | String | No | Must match standard 10-character Indian PAN format. |
  | `email` | String | No | Valid email format. |
  | `mobile_no` | String | No | Max length 20. |
* **Request JSON Example**:
  ```json
  {
    "name": "John Doe",
    "address": "Flat 4B, Emerald Crest, Bangalore",
    "pan": "XYZAB1234C",
    "email": "john.doe@acme.com",
    "mobile_no": "9876543211"
  }
  ```
* **Success Response (200 OK)**:
  ```json
  {
    "id": "6a0e8400-e29b-41d4-a716-446655440111",
    "user_id": "c6c27fc7-73fc-4cdd-8864-954a9c4d760c",
    "name": "John Doe",
    "address": "Flat 4B, Emerald Crest, Bangalore",
    "pan": "XYZAB1234C",
    "email": "john.doe@acme.com",
    "mobile_no": "9876543211",
    "created_at": "2026-06-04T06:13:00.000000+05:30",
    "updated_at": "2026-06-04T06:17:00.000000+05:30"
  }
  ```
* **Curl Example**:
  ```bash
  curl -X POST http://localhost:8000/api/v1/profile/signatory \
       -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
       -H "Content-Type: application/json" \
       -d '{"name": "John Doe", "pan": "XYZAB1234C"}'
  ```

---

### 4. Excel Processing

#### Validate & Store Excel
* **Method**: `POST`
* **Path**: `/validate-excel`
* **Auth**: Bearer Authorization.
* **Request Content-Type**: `multipart/form-data`
* **Request Body**:
  * `file`: (Binary Excel `.xlsx` file upload)
* **Success Response (200 OK)**:
  ```json
  {
    "message": "Excel validated and stored successfully.",
    "validation_result": {
      "success": true,
      "totalRecords": 1,
      "validRecords": 1,
      "invalidRecords": 0,
      "errors": []
    },
    "storage_url": "https://skzceavurcikyajjtpar.supabase.co/storage/v1/object/sign/appointment_excel_files/57d2eca80483447ea353a886dfde44b1.xlsx?token=eyJhbGciOiJIUzI1NiIsIn..."
  }
  ```
* **Validation Failure Response (200 OK but success=false)**:
  * When row validations fail, the request still returns `200 OK`, but the inner `success` is `false`, showing a list of all flagged errors (row number `recId`, column `fieldName`, and descriptive reason `errorMessage`).
  * The file **is not stored in Supabase storage** if validations fail.
  ```json
  {
    "message": "Excel validation failed.",
    "validation_result": {
      "success": false,
      "totalRecords": 10,
      "validRecords": 1,
      "invalidRecords": 9,
      "errors": [
        {
          "recId": 2,
          "fieldName": "Name of employee",
          "errorMessage": "employee name shouldn't consist special characters except . and space"
        },
        {
          "recId": 3,
          "fieldName": "Date of birth",
          "errorMessage": "date of birth should be in dd-mm-yyyy format"
        }
      ]
    },
    "storage_url": null
  }
  ```
* **Curl Example**:
  ```bash
  curl -X POST http://localhost:8000/validate-excel \
       -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
       -F "file=@/path/to/employee_records.xlsx"
  ```

---

## 📋 Summary of Excel Validation Rules

When uploading an Excel sheet, row values are parsed and validated column-by-column. Below is a summary of the constraints applied:

| Field Name | Required? | Rules & Format | Error Message |
| :--- | :--- | :--- | :--- |
| **Name of employee** | Yes | Only alphabets, spaces, and dots (`.`) | *employee name shouldn't consist special characters except . and space* |
| **Date of birth** | Yes | Must be in `dd-mm-yyyy` format | *date of birth should be in dd-mm-yyyy format* |
| **Father's / Mother's name** | Yes | Only alphabets, spaces, and dots (`.`) | *parent name shouldn't consist special characters except . and space* |
| **Aadhaar number** | Yes | Exactly 12 digits (numeric) | *aadhaar number should be 12 digits only numeric* |
| **Labour Identification Number (LIN)** | Yes | Alphanumeric including any special characters | *Labour Identification Number (LIN) of the establishment is required* |
| **UAN / ESIC** | No | If provided, exactly 12 digits (numeric) | *UAN/ESIC should be 12 digits only numeric* |
| **Designation** | No | No digits allowed (alphabets, spaces, and punctuation only) | *designation should contain only alphabets, spaces and special characters* |
| **Basic Pay** | No | Must be a valid positive number | *basic pay should be a numeric value* |
| **Dearness Allowance** | No | Must be a valid positive number | *dearness allowance should be a numeric value* |
| **Other Allowance** | No | Must be a valid positive number | *other allowance should be a numeric value* |
| **Broad nature of duties** | No | Word count cannot exceed 100 words | *text should not exceed 100 words* |
| **Date of Joining** | No | Must be in `dd-mm-yyyy` format if provided | *date of joining should be in dd-mm-yyyy format* |
