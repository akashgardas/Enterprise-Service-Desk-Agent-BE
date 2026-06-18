# Enterprise Service Desk Agent - Backend

AI-powered support management backend built with FastAPI, MongoDB Atlas, and Google Gemini for intelligent ticket handling, authentication, knowledge base retrieval, and analytics.

---

# Overview

Enterprise Service Desk Agent is a modern support management platform designed to automate enterprise support operations through AI-assisted troubleshooting, ticket management, knowledge base retrieval, and analytics.

The backend exposes REST APIs and WebSocket services that power employees, service desk agents, managers, and administrators.

---

# Features

## Authentication & Security

* JWT Authentication
* Refresh Tokens
* Role-Based Access Control (RBAC)
* Multi-Factor Authentication (MFA)
* Password Reset
* Password Hashing with bcrypt
* Account Lockout Protection

---

## AI Support Assistant

* Natural Language Conversations
* Context-Aware Responses
* Google Gemini Integration
* Suggested Solutions
* Chat Session Management
* Conversation History

---

## Ticket Management

* Ticket Creation
* Automatic Ticket Classification
* Ticket Assignment
* Status Tracking
* Priority Management
* Resolution Tracking
* Escalation Workflow

---

## Knowledge Base

* Search Articles
* AI-assisted Retrieval
* Categorized Documents
* Self-Service Support

---

## Notifications

* Ticket Created Notifications
* Assignment Notifications
* Ticket Updates
* Resolution Notifications

---

## Analytics

* Open Ticket Count
* Closed Ticket Count
* Average Resolution Time
* SLA Monitoring
* Agent Performance Metrics
* Reporting Dashboard APIs

---

# Tech Stack

| Category          | Technology       |
| ----------------- | ---------------- |
| Framework         | FastAPI          |
| Language          | Python 3.10+     |
| Database          | MongoDB Atlas    |
| Driver            | Motor            |
| Validation        | Pydantic v2      |
| Authentication    | JWT + PyJWT      |
| Password Hashing  | Passlib (bcrypt) |
| MFA               | PyOTP            |
| AI Engine         | Google Gemini    |
| ML                | Scikit-learn     |
| Communication     | WebSockets       |
| API Documentation | Swagger/OpenAPI  |
| Version Control   | Git + GitHub     |

---

# System Architecture

```text
React Frontend
      │
      ▼
FastAPI Backend
      │
      ├── MongoDB Atlas
      │
      ├── Gemini AI
      │
      └── WebSockets
```

---

# Project Structure

```text
app/
│
├── routers/
│    ├── auth.py
│    ├── tickets.py
│    ├── analytics.py
│    ├── chat.py
│    └── kb.py
│
├── services/
├── models/
├── schemas/
├── dependencies/
├── utils/
├── database.py
├── config.py
└── main.py

tests/

requirements.txt
```

---

# Installation

## Clone Repository

```bash
git clone <repository-url>
cd backend
```

---

## Create Virtual Environment

### Windows

```bash
python -m venv .venv

.venv\Scripts\activate
```

### Linux/macOS

```bash
python -m venv .venv

source .venv/bin/activate
```

---

## Install Dependencies

```bash
pip install -r requirements.txt
```

---

# Environment Variables

Create:

```text
.env
```

Example:

```env
MONGO_URI=

DATABASE_NAME=

JWT_SECRET_KEY=

JWT_REFRESH_SECRET=

ACCESS_TOKEN_EXPIRE_MINUTES=30

REFRESH_TOKEN_EXPIRE_DAYS=7

GEMINI_API_KEY=

SMTP_USERNAME=

SMTP_PASSWORD=

MOCK_SERVICES=False

ALLOWED_ORIGINS=["http://localhost:5173"]
```

---

# Run Server

Development:

```bash
uvicorn app.main:app --reload
```

Server:

```text
http://localhost:8000
```

---

# API Documentation

Swagger UI

```text
http://localhost:8000/docs
```

ReDoc

```text
http://localhost:8000/redoc
```

---

# WebSocket Support

Real-time communication for:

* AI Chat
* Notifications
* Live Updates

Example:

```text
ws://localhost:8000/chat/ws
```

---

# Database Collections

```text
users

tickets

ticket_history

chat_history

notifications

knowledge_base

audit_logs

password_reset_tokens
```

---

# Machine Learning Features

## Ticket Deduplication

Implemented using:

* TF-IDF Vectorization
* Cosine Similarity

Purpose:

* Detect duplicate tickets
* Prevent redundant support efforts

---

# Health Check

Endpoint:

```text
GET /
```

Response:

```json
{
  "status": "healthy",
  "database": "connected"
}
```

---

# Available Routers

## Authentication

```text
/auth
```

## Tickets

```text
/tickets
```

## Knowledge Base

```text
/kb
```

## Chat

```text
/chat
```

## Analytics

```text
/analytics
```

---

# CI/CD Pipeline

```text
Developer
     │
     ▼
Push to dev
     │
     ▼
Pull Request
     │
     ▼
GitHub Actions

• Install Dependencies
• Validate Imports
• Run Tests

     │
     ▼
Merge to main
     │
     ▼
Render Auto Deploy
```

---

# Deployment

| Component      | Platform       |
| -------------- | -------------- |
| Backend        | Render         |
| Database       | MongoDB Atlas  |
| AI Engine      | Google Gemini  |
| Source Control | GitHub         |
| CI             | GitHub Actions |

---

# Future Enhancements

* Voice-based AI Support
* Predictive Analytics
* Advanced LLM Agents
* Real-time Notifications
* Docker Support
* Kubernetes Deployment
* Microservices Architecture
* Single Sign-On (SSO)
* Biometric Authentication
* Multi-language Support

---

# Contributors

* Backend Team
* AI Team
* DevOps Team

---

# License

MIT License

---

Built with FastAPI, MongoDB Atlas, Motor, JWT, WebSockets, Scikit-Learn, and Google Gemini.
