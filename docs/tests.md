# Test Suite Documentation

This document provides an overview of the test suite for the Astrometry.net Lite project, covering both backend (Python/FastAPI) and frontend (React/TypeScript) testing.

**Live Demo:** [https://astrometry.yage.ai/](https://astrometry.yage.ai/)

## Test Structure

```
tests/
├── unit/                           # Backend unit tests
│   ├── conftest.py                # Shared fixtures
│   ├── services/                  # Service layer tests
│   │   ├── test_jobs.py          # Job management service
│   │   ├── test_submissions.py   # Submission handling
│   │   ├── test_queue.py         # Message queue service
│   │   ├── test_storage.py       # File storage operations
│   │   └── test_ids.py           # ID sequence generation
│   ├── api/                       # API route tests
│   │   ├── test_routes_legacy.py # Legacy API endpoints
│   │   └── test_routes_frontend.py # Frontend API endpoints
│   └── domain/                    # Domain model tests
│       ├── test_models.py        # Pydantic model validation
│       └── test_enums.py         # Enum definitions
└── integration/                   # Integration tests
    ├── test_e2e.py               # End-to-end workflow
    ├── test_backend_flow.py      # Backend flow testing
    ├── test_service.py           # Full service testing
    └── test_annotator.py         # Annotation generation

frontend/src/
├── test/
│   ├── setup.ts                  # Test environment setup
│   └── mocks/
│       ├── handlers.ts           # MSW request handlers
│       └── server.ts             # MSW server instance
├── api.test.ts                   # API client tests
└── hooks/
    ├── useJobList.test.ts        # Job list hook tests
    └── useJobDetail.test.ts      # Job detail hook tests
```

## Backend Tests (Python/pytest)

### Test Frameworks
- **pytest** - Main test framework
- **pytest-asyncio** - Async test support
- **unittest.mock** - Mocking utilities

### Coverage Areas

#### Service Layer (`tests/unit/services/`)
Tests for core business logic:

- **Job Service** (`test_jobs.py`)
  - Job retrieval by ID
  - Status updates and transitions
  - Artifact management
  - Job listing and filtering

- **Submission Service** (`test_submissions.py`)
  - API key validation
  - Submission creation workflow
  - Status marking (started/finished)
  - Job-submission associations

- **Queue Service** (`test_queue.py`)
  - Job enqueueing
  - Message leasing with visibility timeout
  - Completion and failure handling

- **Storage Service** (`test_storage.py`)
  - Directory management
  - File save/copy operations

- **ID Service** (`test_ids.py`)
  - Sequence generation
  - Counter initialization

#### API Routes (`tests/unit/api/`)
Tests for HTTP endpoints:

- **Legacy API** (`test_routes_legacy.py`)
  - Authentication (login)
  - Job status queries
  - Calibration data retrieval
  - Tags and annotations
  - Unsupported feature handling

- **Frontend API** (`test_routes_frontend.py`)
  - Paginated job listing
  - Job detail with stage info
  - Log streaming
  - Original file access

#### Domain Models (`tests/unit/domain/`)
Tests for data structures:

- **Models** (`test_models.py`)
  - Job, Submission, Artifact, QueueMessage validation
  - Field defaults and relationships

- **Enums** (`test_enums.py`)
  - JobStatus, SubmissionStatus, ArtifactType values

### Running Backend Tests

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run specific module
pytest tests/unit/services/test_jobs.py -v

# Run with coverage
pytest tests/unit/ --cov=services --cov-report=html
```

## Frontend Tests (TypeScript/Vitest)

### Test Frameworks
- **Vitest** - Fast test runner for Vite
- **React Testing Library** - Component testing
- **MSW (Mock Service Worker)** - API mocking

### Coverage Areas

#### API Client (`src/api.test.ts`)
Tests for fetch functions:
- Job list fetching with pagination
- Job detail retrieval
- Log streaming
- Status filtering

#### Hooks (`src/hooks/`)
Tests for React hooks:

- **useJobList** (`useJobList.test.ts`)
  - Initial data loading
  - Pagination state
  - Refresh functionality

- **useJobDetail** (`useJobDetail.test.ts`)
  - Job detail fetching
  - Calibration data access
  - Artifact URLs
  - Log content loading

### Running Frontend Tests

```bash
cd frontend

# Run tests in watch mode
npm test

# Run once
npm run test:run

# Run with coverage
npm run test:coverage
```

## Mock Strategy

### Backend Mocking
- MongoDB collections are mocked using `AsyncMock`
- Custom `AsyncCursor` class for async iteration
- File system operations patched with `unittest.mock.patch`

### Frontend Mocking
- MSW intercepts HTTP requests at the network level
- Handlers return realistic test data
- Full URL matching for API endpoints

## Test Statistics

| Category | Test Count |
|----------|------------|
| Backend Unit Tests | 85 |
| Frontend Unit Tests | 22 |
| **Total** | **107** |

## CI/CD Integration

Example GitHub Actions workflow:

```yaml
name: Tests
on: [push, pull_request]

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -e ".[dev]"
      - run: pytest tests/unit/ -v

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm ci
      - run: npm run test:run
```
