# MagicTale AI Backend 📚✨

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![Django](https://img.shields.io/badge/Django-5.0-green?logo=django)
![Celery](https://img.shields.io/badge/Celery-Async-green)
![Docker](https://img.shields.io/badge/Docker-Ready-blue?logo=docker)

MagicTale is an AI-powered storytelling platform designed for children. It generates personalized stories, vibrant cover illustrations (DALL-E 3), and professional voice narration (ElevenLabs) based on user prompts. The backend relies on an asynchronous pipeline to manage long-running AI generation tasks via WebSockets.

---

## 🚀 Tech Stack

- **Framework:** Django 5, Django REST Framework (DRF)
- **Asynchronous Tasks:** Celery + Redis
- **Real-time Updates:** Django Channels (Daphne) + WebSockets
- **Database:** PostgreSQL
- **Authentication:** SimpleJWT (Email/Password), Google OAuth2, Apple Sign-In
- **AI Services:**
  - OpenAI (GPT-4o for Text, DALL-E 3 for Images)
  - ElevenLabs (Text-to-Speech)
- **Push Notifications:** Firebase Cloud Messaging (FCM)
- **Payments:** RevenueCat Webhooks
- **Infrastructure:** Docker, Nginx

---

## 🛠 Installation & Setup

### Prerequisites

- Docker & Docker Compose
- Firebase Service Account JSON file (`serviceAccountKey.json`)
- API Keys (OpenAI, ElevenLabs, RevenueCat)

### 1. Clone the Repository

```bash
git clone https://github.com/kaisarfardin6620/magictale.git
cd magictale
```

### 2. Environment Configuration

Create a `.env` file in the root directory. You can copy the structure below:

```dotenv
# Security
SECRET_KEY="your_long_random_string"
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,your-production-ip
CSRF_TRUSTED_ORIGINS=http://localhost:3000,https://your-domain.com

# Database & Redis
DATABASE_URL="postgres://user:password@host:5432/db_name"
REDIS_URL="redis://redis-cache:6379"

# AI Keys
OPENAI_API_KEY="sk-..."
ELEVENLABS_API_KEY="sk-..."

# Authentication (Apple/Google)
GOOGLE_CLIENT_ID="..."
GOOGLE_CLIENT_SECRET="..."
APPLE_CLIENT_ID="..."
APPLE_TEAM_ID="..."
APPLE_KEY_ID="..."
# Paste the content of your .p8 file here
APPLE_CERTIFICATE_CONTENT="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"

# Firebase (Push Notifications)
FIREBASE_SERVICE_ACCOUNT_PATH="serviceAccountKey.json"

# RevenueCat
REVENUECAT_WEBHOOK_AUTH_HEADER="Basic your_secret"
REVENUECAT_API_KEY="..."
```

### 3. Build and Run (Docker)

Ensure your `serviceAccountKey.json` is in the root folder.

```bash
docker-compose up --build -d
```

The application will start on:
- **Via Nginx:** Port 8040
- **Direct container:** Port 8000

Migrations and Static files are handled automatically by the entrypoint script.

---

## 📚 API Documentation

**Base URL:** `http://your-server-ip/api`

### 🌐 Interactive API Reference

MagicTale provides auto-generated OpenAPI 3.0 documentation using `drf-spectacular`.

You can explore the interactive API documentation via the following endpoints:

- **Swagger UI:** `http://localhost:8040/api/docs/` (or `your-domain/api/docs/`) - Provides an interactive UI to test API endpoints directly.
- **ReDoc:** `http://localhost:8040/api/redoc/` (or `your-domain/api/redoc/`) - Offers a clean, readable reference layout.
- **OpenAPI Schema:** `http://localhost:8040/api/schema/` (or `your-domain/api/schema/`) - The raw YAML/JSON schema definition.

> **Note:** To test secured endpoints in Swagger UI, click the **Authorize** button at the top and enter your JWT access token.

### 🔐 Authentication

#### 1. Login

**Endpoint:** `POST /auth/login/`

**Request:**

```json
{
  "email": "user@example.com",
  "password": "SecretPassword123!"
}
```

**Response:**

```json
{
  "success": true,
  "data": {
    "token": "access_token_jwt...",
    "refresh_token": "refresh_token...",
    "full_name": "John Doe",
    "id": 1
  }
}
```

#### 2. Register Device (Push Notifications)

Update the FCM token for the logged-in user.

**Endpoint:** `POST /auth/devices/register/`

**Header:** `Authorization: Bearer <token>`

**Request:**

```json
{
  "registration_id": "fcm_token_string_from_firebase_sdk",
  "type": "android"
}
```

(Type options: `android`, `ios`, `web`)

#### 3. Social Login

**Google Login:** `POST /auth/google/`

```json
{ "access_token": "google_oauth_token" }
```

**Apple Login:** `POST /auth/apple/`

```json
{ "access_token": "...", "id_token": "..." }
```

---

### 📖 Story Generation

#### 1. Get Generation Options

Fetch available themes, art styles, and voices.

**Endpoint:** `GET /ai/generation-options/`

#### 2. Create a Story

**Endpoint:** `POST /ai/stories/`

**Header:** `Authorization: Bearer <token>`

**Request:**

```json
{
  "hero": {
    "child_name": "Leo",
    "age": 5,
    "pronouns": "he/him",
    "favorite_animal": "Lion",
    "favorite_color": "Blue"
  },
  "theme": "space",
  "art_style": "pixar",
  "length": "short",
  "difficulty": 2
}
```

**Response:** `202 Accepted` (Generation starts in background)

#### 3. List Stories

**Endpoint:** `GET /ai/stories/`

#### 4. Get Story Detail

**Endpoint:** `GET /ai/stories/{id}/`

Returns text, image URL, audio URL, and processing status.

---

### ⚡ Real-Time Progress (WebSockets)

Connect to the WebSocket to receive live updates on story generation (e.g., "Writing text...", "Generating images...", "Recording audio...").

**URL:** `ws://your-domain/ws/ai/stories/{project_id}/?token={access_token}`

**Events Received:**

```json
{
  "status": "running",
  "progress": 40,
  "message": "Drawing the cover image..."
}
```

---

### 💳 Subscriptions & Payments

#### 1. Check Status

**Endpoint:** `GET /subscriptions/status/`

#### 2. Sync with RevenueCat

**Endpoint:** `POST /subscriptions/sync/`

Force syncs the local database with RevenueCat entitlements.

---

## 🏗 Architecture & Workflows

### Story Pipeline

1. **Stage 1 (Text):** GPT-4o generates the story text
2. **Stage 2 (Metadata & Art):** System analyzes text for tags/synopsis and generates a DALL-E 3 cover image
3. **Stage 3 (Audio):** ElevenLabs converts text to speech per page
4. **Completion:** Audio is stitched together, uploaded to storage, and a Push Notification is sent

### Notification System

- Uses `fcm-django` with the Firebase Admin SDK (`FCM_CREDENTIALS`)
- Triggers on: Story Completion, Profile Updates, Password Resets

### Security

- Passwords validated against Pwned Passwords API
- WebSockets protected by JWT and ownership checks
- RevenueCat Webhooks protected by Auth Headers

---

## 🔗 Repository

**GitHub:** [magictale](https://github.com/kaisarfardin6620/magictale.git)

---

## 📝 License

This project is proprietary software. All rights reserved.

**Developed by:** Kaisar Fardin