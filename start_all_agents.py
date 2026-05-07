import subprocess
import time
import sys
import os

def start_agent(name, port):
    print(f"Starting {name} agent on port {port}...")
    # Use the same server script for all but specify different ports if needed
    # Actually, our unified server handles all routes, but we can start multiple instances
    # to simulate the distributed nature as per the cards.
    return subprocess.Popen([
        sys.executable, 
        "a2a/agent_server.py", 
        "--port", str(port),
        "--agent", name.lower().replace(" ", "_")
    ])

if __name__ == "__main__":
    agents = [
        ("document_parser", 8001),
        ("validator", 8002),
        ("router", 8003)
    ]
    
    processes = []
    try:
        for name, port in agents:
            p = start_agent(name, port)
            processes.append(p)
            time.sleep(1) 
            
        print("\nAll agents started. Press Ctrl+C to stop.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping agents...")
        for p in processes:
            p.terminate()
        print("Done.")
