@echo off
REM AgentGeneral server startup script
REM Uses --reload-exclude to prevent uvicorn from restarting when skills/memory files change.
REM Without this, writing temp skill files during health-checks triggers a reload mid-job.

cd /d "C:\Users\Wisdom Mboya\Desktop\Projects\agentgeneral"

python -m uvicorn server:app ^
    --host 0.0.0.0 ^
    --port 8765 ^
    --reload ^
    --reload-exclude "skills/*" ^
    --reload-exclude "memory/*" ^
    --reload-exclude "*.faiss" ^
    --reload-exclude "*.json"