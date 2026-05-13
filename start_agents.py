"""
Start all A2A agents for the Insurance Intake System

Run this script to start all three specialist agents and the orchestrator.
Requires 4 terminal windows or use start command on Windows.

If adk web shows 404 for /.well-known/agent.json: something else is bound to
8001–8003 (often a stale non-A2A process). Stop those processes, then run
this script so document_parser/validator/router (to_a2a) own those ports.
"""
import subprocess
import sys
import time
import os
import shlex

ROOT = os.path.dirname(os.path.abspath(__file__))


def start_agent(relative_script: str, name: str, port: int):
    """Start an agent in a new terminal window (cwd = project root)."""
    script_full = os.path.join(ROOT, relative_script)
    if sys.platform == "win32":
        rel = relative_script.replace("/", "\\")
        cmd = f'start cmd /k "title {name} && cd /d {ROOT} && python {rel}"'
        subprocess.Popen(cmd, shell=True)
    else:
        inner = f"cd {shlex.quote(ROOT)} && python {shlex.quote(script_full)}; exec bash"
        cmd = f"gnome-terminal -- bash -c {shlex.quote(inner)}"
        subprocess.Popen(cmd, shell=True)
    
    print(f" Started {name} on port {port}")
    time.sleep(2)

if __name__ == "__main__":
    print(" Starting Insurance Intake Multi-Agent System...")
    print("=" * 60)
    
    # Start A2A-compliant specialist servers (must expose /.well-known/agent.json)
    start_agent("document_parser/main.py", "DocumentParserA2A", 8001)
    start_agent("validator/main.py", "ValidatorA2A", 8002)
    start_agent("router/main.py", "RouterA2A", 8003)
    
    print("\n Waiting for specialist agents to initialize...")
    time.sleep(3)
    
    print("\n Now start the orchestrator manually:")
    print("   Run: adk web")
    print("   Then open: http://localhost:8000")
    print("\n" + "=" * 60)
    print(" All specialist agents are running!")
    print("   - DocumentParser: http://localhost:8001")
    print("   - ValidatorAgent: http://localhost:8002")
    print("   - RouterAgent:    http://localhost:8003")
    print("\nPress Ctrl+C to stop this script (agents will keep running)")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n Startup script stopped. Agents are still running in separate windows.")
