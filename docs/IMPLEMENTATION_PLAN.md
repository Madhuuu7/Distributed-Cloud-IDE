# Distributed Cloud IDE - Implementation Plan

## 1. Project Summary

This project will be a portfolio-grade full-stack web application that simulates a cloud-style integrated development environment. The experience will combine:

- a polished React-based frontend
- a FastAPI backend with SQLite persistence
- JWT-based authentication
- a Monaco-powered editor
- file management and code execution
- an AI assistant panel for coding support

The goal is to deliver a product that feels complete, visually refined, and technically impressive without overcomplicating the initial build.

---

## 2. Product Vision

The application should allow a user to:

- sign up and log in securely
- access a personal dashboard
- browse and manage files in a workspace
- open files in a Monaco editor
- save changes to the backend
- run Python and JavaScript code
- interact with an AI assistant for help, explanations, and code suggestions

This should feel like a lightweight but believable cloud IDE experience rather than a toy demo.

---

## 3. Recommended Architecture

### 3.1 Frontend

Technology choices:
- React
- Vite
- TypeScript
- Tailwind CSS
- Monaco Editor

Responsibilities:
- render authentication screens
- provide dashboard and workspace layout
- manage file explorer state
- host Monaco editor and file actions
- communicate with backend APIs
- display execution results and AI responses

Suggested structure:
- App shell with sidebar, top bar, and main content area
- Route-based pages for login, signup, dashboard, editor, and workspace views
- reusable UI components for buttons, panels, modals, cards, and forms

### 3.2 Backend

Technology choices:
- FastAPI
- SQLAlchemy
- SQLite
- JWT Authentication

Responsibilities:
- handle authentication and user sessions
- persist users, workspaces, and file metadata
- manage file create/open/save operations
- execute Python and JavaScript code securely
- expose AI assistant endpoints

### 3.3 Data Model

Core entities:
- User
  - id
  - email
  - password_hash
  - created_at
- Project or Workspace
  - id
  - name
  - owner_id
  - created_at
- FileNode
  - id
  - project_id
  - name
  - path
  - content
  - language
  - created_at
  - updated_at
- ExecutionLog (optional but valuable)
  - id
  - user_id
  - file_id
  - language
  - status
  - output
  - created_at

### 3.4 Storage Approach

For a portfolio project, the best balance is:
- SQLite for relational metadata and user data
- actual project files stored on disk in a local workspace directory

Example layout:
- server/workspaces/{user_id}/{project_id}/...

This keeps the implementation simple while still feeling realistic.

### 3.5 Execution Model

Code execution should be handled server-side through subprocess execution:
- Python code runs via python
- JavaScript runs via node

The backend will:
- accept code payloads
- run them with runtime timeouts
- capture stdout/stderr
- return structured result objects

Security note: execution should be restricted and sandboxed as much as possible. For a portfolio project, local subprocess execution is acceptable initially, with future expansion to containers or remote workers.

### 3.6 AI Assistant Model

The AI panel should be designed as a modular feature:
- first phase: mock or template-based responses
- second phase: connect to an LLM provider such as OpenAI or Anthropic

This phased approach keeps delivery realistic and avoids blocking the rest of the project on external API integration.

---

## 4. Proposed Folder Structure

```text
Distributed-Cloud-IDE/
├── docs/
│   └── IMPLEMENTATION_PLAN.md
├── client/
│   ├── public/
│   ├── src/
│   │   ├── assets/
│   │   ├── components/
│   │   │   ├── auth/
│   │   │   ├── layout/
│   │   │   ├── editor/
│   │   │   ├── explorer/
│   │   │   └── ai/
│   │   ├── pages/
│   │   │   ├── LoginPage.tsx
│   │   │   ├── SignupPage.tsx
│   │   │   ├── DashboardPage.tsx
│   │   │   └── WorkspacePage.tsx
│   │   ├── hooks/
│   │   ├── services/
│   │   ├── contexts/
│   │   ├── types/
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   └── package.json
├── server/
│   ├── app/
│   │   ├── api/
│   │   │   ├── auth.py
│   │   │   ├── files.py
│   │   │   ├── execution.py
│   │   │   └── ai.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── deps.py
│   │   ├── db/
│   │   │   ├── base.py
│   │   │   ├── session.py
│   │   │   └── init_db.py
│   │   ├── models/
│   │   │   ├── user.py
│   │   │   ├── workspace.py
│   │   │   └── file.py
│   │   ├── schemas/
│   │   │   ├── auth.py
│   │   │   ├── file.py
│   │   │   └── execution.py
│   │   ├── services/
│   │   │   ├── auth_service.py
│   │   │   ├── file_service.py
│   │   │   ├── execution_service.py
│   │   │   └── ai_service.py
│   │   └── main.py
│   ├── workspaces/
│   ├── requirements.txt
│   └── .env.example
├── shared/
│   └── types/
├── README.md
└── .gitignore
```

---

## 5. Implementation Phases

### Phase 0 - Foundation and Setup

Objective:
Set up the base project structure and development workflow.

Tasks:
- initialize Vite React TypeScript frontend
- initialize FastAPI backend
- configure Tailwind CSS and Monaco Editor
- create shared environment variables and project conventions
- define API contract structure

Deliverables:
- working frontend shell
- working backend skeleton
- development environment ready for feature work

### Phase 1 - Authentication and User Accounts

Objective:
Create secure account flows for login and signup.

Tasks:
- create SQLAlchemy user model
- implement password hashing
- build JWT authentication flow
- add login and signup API endpoints
- connect frontend forms to backend
- protect private routes

Deliverables:
- secure register/login experience
- authenticated user sessions
- route protection for private areas

### Phase 2 - Workspace and File Management

Objective:
Create the core IDE workspace experience.

Tasks:
- define workspace/project model
- implement file tree creation, listing, and navigation
- add file create/open/save operations
- support file content persistence in SQLite and disk storage
- design the dashboard and workspace layout

Deliverables:
- functional file explorer
- ability to create and edit files
- save/open workflow for files

### Phase 3 - Monaco Editor Integration

Objective:
Provide a polished code editing experience.

Tasks:
- integrate Monaco Editor into the workspace view
- support file language detection
- handle editor content changes and save actions
- create clean editor layout with split panels if desired
- implement file tab or selection behavior

Deliverables:
- full editor experience with syntax highlighting
- file save behavior tied to backend storage

### Phase 4 - Code Execution Engine

Objective:
Allow users to run code from the editor.

Tasks:
- build execution endpoints for Python and JavaScript
- capture stdout/stderr and execution errors
- design a results panel in the UI
- add run buttons and status messaging
- handle timeouts and basic error reporting

Deliverables:
- code execution workflow for Python and JavaScript
- visible output panel with useful diagnostics

### Phase 5 - AI Assistant Panel

Objective:
Add a modern AI-assisted coding experience.

Tasks:
- create UI panel for chat or command-style interaction
- implement backend endpoint for AI requests
- support prompt-to-response flows
- add typing indicators and message history
- optionally include file-aware prompts in the future

Deliverables:
- functional AI assistant panel
- polished interaction model
- architecture ready for future LLM integration

### Phase 6 - Polish, Testing, and Deployment

Objective:
Turn the project into a portfolio-quality presentation.

Tasks:
- improve visual design and responsiveness
- add loading states, empty states, and error handling
- write tests for auth, file operations, and execution flows
- review security and basic reliability concerns
- prepare deployment configuration

Deliverables:
- production-ready UI polish
- reliable core flows
- deployment-ready project

---

## 6. Execution Plan

### Sprint 1 - Foundation

Focus:
- scaffold frontend and backend
- establish project conventions
- configure styling and routing

Outcomes:
- app boots successfully
- folder structure is in place
- initial shell UI is visible

### Sprint 2 - Authentication and Workspace Basics

Focus:
- auth endpoints and UI
- project/dashboard pages
- file storage foundation

Outcomes:
- login/signup work
- dashboard renders user context
- basic workspace scaffold exists

### Sprint 3 - Editor and Persistence

Focus:
- Monaco integration
- open/save file flow
- file explorer interaction

Outcomes:
- editor works end-to-end
- files persist across sessions

### Sprint 4 - Execution and AI

Focus:
- run Python and JavaScript
- results panel
- AI assistant interface

Outcomes:
- users can execute code directly
- AI panel responds meaningfully

### Sprint 5 - Polish and Hardening

Focus:
- UX improvements
- error handling
- tests and documentation

Outcomes:
- polished portfolio experience
- smoother developer workflow

---

## 7. Suggested UX Flow

1. User lands on a landing or login page.
2. User signs up or logs in.
3. User reaches the dashboard and creates or opens a workspace.
4. User sees a file explorer and editor side by side.
5. User edits a file and saves it.
6. User runs code and reviews output.
7. User opens the AI assistant for help or explanation.

This flow should feel intuitive and visually coherent.

---

## 8. Technical Risks and Mitigations

### Risk: Code execution security
Mitigation:
- use subprocess with strict timeouts
- avoid exposing full system access
- keep initial scope local and controlled

### Risk: Authentication complexity
Mitigation:
- implement standard JWT flow with password hashing from the start
- keep auth endpoints simple and well-scoped

### Risk: File handling inconsistencies
Mitigation:
- define clear rules for file paths and naming
- validate user input carefully

### Risk: AI integration becoming a blocker
Mitigation:
- implement mock responses first
- switch to real provider later once the UI and backend wiring are stable

### Risk: Too much scope too early
Mitigation:
- prioritize MVP features first
- treat advanced polish as phase 6 rather than phase 1

---

## 9. Definition of Done

The project will be considered complete when all core features are working:

- login and signup
- dashboard
- file explorer
- Monaco editor
- save/open files
- Python and JavaScript execution
- AI assistant panel
- polished UI and responsive layout
- basic tests and deployment readiness

---

## 10. Recommended Build Order

1. Set up client and server foundations
2. Build auth flow
3. Build workspace and files
4. Integrate Monaco editor
5. Add code execution
6. Add AI assistant
7. Polish and deploy

This order ensures the most essential product experience is delivered first while leaving room for quality improvements.
