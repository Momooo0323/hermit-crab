@echo off
title Hermit Crab (CLI)
cd /d "%~dp0"
echo  Hermit Crab - CLI Mode
echo  Make sure your backend (llama-server / OpenAI / Anthropic) is configured.
echo.
python agent.py
pause
