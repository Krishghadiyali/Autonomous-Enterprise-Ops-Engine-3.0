from fastapi import FastAPI
from dotenv import load_dotenv
from app.routers import agent

# uvicorn app.main:app --reload
# app.main tells it to look in the app folder for the main.py file.
# :app tells it to target the app = FastAPI() instance.
# --reload automatically restarts the server when you save code changes.

# Load environment variables from .env BEFORE initializing the app
load_dotenv()

# Initialize the FastAPI application (Similar to const app = express())
app = FastAPI(
    title="Autonomous Enterprise Ops Engine",
    description="Backend API for Agentic RAG and SQL workflow execution",
    version="1.0.0"
)

# Attach the agent router (Equivalent to app.use('/agent', agentRouter))
app.include_router(agent.router)

# Define a basic health check route (Similar to app.get('/health', ...))
@app.get("/health")
def health_check():
    """Verify the API is running before testing complex AI routes."""
    return {"status": "online", "system": "ops_engine_active"}