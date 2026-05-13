import subprocess
import time
import sys
import os

def start_agent(script_path: str, name: str, port: int):
    print(f"Starting {name} on port {port} ({script_path})...")
    return subprocess.Popen([sys.executable, script_path], cwd=os.path.dirname(os.path.abspath(__file__)))


if __name__ == "__main__":
    agents = [
        ("document_parser/main.py", "DocumentParserA2A", 8001),
        ("validator/main.py", "ValidatorA2A", 8002),
        ("router/main.py", "RouterA2A", 8003),
    ]

    processes = []
    try:
        for script_path, display_name, port in agents:
            p = start_agent(script_path, display_name, port)
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
