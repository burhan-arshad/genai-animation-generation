Set-Location D:\AntiGravity\shorts-agent
New-Item -ItemType Directory -Force logs | Out-Null
.\.venv\Scripts\python.exe -m shorts_agent.daily *>> logs\daily.log
