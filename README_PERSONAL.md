# Lumine Hedge Fund - Personal Development

**My trading platform for XAUUSD and other instruments.**

## Quick Start

```bash
# Install dependencies
cd backend && pip install -e .[dev]
cd ../frontend && npm install

# Run tests
pytest backend/tests/ -v

# Start services
docker-compose up -d postgres redis

# Run backend
python -m uvicorn src.lumine.api.app:app --reload

# Run frontend  
npm run dev
```

## What's Built

✅ Backend API (FastAPI)
✅ Database migrations (PostgreSQL + SQLAlchemy)
✅ Trading core logic
✅ TCA calculation
✅ Agent orchestration framework
✅ Test suite (500+ unit tests)

## Next Steps

Just keep coding! No approvals needed. Deploy when ready.

## Notes

- This is my personal project
- Use whatever works best for me
- Deploy to VPS when feature-complete
