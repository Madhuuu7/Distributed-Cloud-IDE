# Distributed Cloud IDE

A portfolio-quality full-stack web application that showcases modern software engineering with a cloud-style IDE experience.

## Stack

### Frontend
- React
- Vite
- TypeScript
- Tailwind CSS
- React Router
- Axios
- Monaco Editor

### Backend
- FastAPI
- SQLAlchemy
- SQLite
- JWT Authentication
- Pydantic
- Uvicorn

## Project Structure

- client/ for the React frontend
- server/ for the FastAPI backend
- docs/ for planning and design notes

## Getting Started

### Frontend

```bash
cd client
npm install
npm run dev
```

### Backend

```bash
cd server
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Notes

This scaffold includes placeholder implementations for the major UI and API entry points so the project can be extended incrementally.
