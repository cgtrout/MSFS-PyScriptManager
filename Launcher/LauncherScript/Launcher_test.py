import psutil
import threading
import random
import time
import socket
from pathlib import Path
from Launcher import ScriptLauncherApp, ScriptTab
import tkinter as tk

def get_python_pids():
    """Get all active Python process PIDs."""
    return {p.pid for p in psutil.process_iter(attrs=["name"]) if p.info["name"] and "python" in p.info["name"].lower()}

def start_network_server(host="127.0.0.1", port=65432, stop_event=None):
    """Start a network server that randomly disconnects or delays clients."""
    def handle_client(conn, addr):
        print(f"[SERVER] Connected to {addr}")
        try:
            while not stop_event.is_set():
                if random.random() < 0.1:
                    print(f"[SERVER] Simulating disconnection for {addr}")
                    conn.close()
                    return
                if random.random() < 0.2:
                    delay = random.uniform(0.5, 2.0)
                    print(f"[SERVER] Simulating delay of {delay:.2f}s for {addr}")
                    time.sleep(delay)
                data = conn.recv(1024)
                if not data:
                    print(f"[SERVER] Client {addr} disconnected")
                    return
                conn.sendall(data)
        except (ConnectionResetError, BrokenPipeError):
            print(f"[SERVER] Connection to {addr} lost.")
        finally:
            conn.close()

    def server_thread():
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind((host, port))
        server.listen()
        print(f"[SERVER] Listening on {host}:{port}")
        try:
            while not stop_event.is_set():
                server.settimeout(1)
                try:
                    conn, addr = server.accept()
                    client_thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
                    client_thread.start()
                except socket.timeout:
                    continue
        finally:
            server.close()

    threading.Thread(target=server_thread, daemon=True).start()

def create_test_script(script_path, server_address):
    """Create a test script that connects to the server and runs indefinitely."""
    script_content = f"""
import socket
import threading
import time

def network_worker(server_address):
    while True:
        try:
            with socket.create_connection(server_address, timeout=5) as sock:
                print("[CLIENT] Connected to server")
                while True:
                    message = f"Hello from thread {{threading.current_thread().name}}"
                    sock.sendall(message.encode())
                    data = sock.recv(1024)
                    print("[CLIENT] Received:", data.decode())
                    time.sleep(1)
        except Exception as e:
            print("[CLIENT] Connection error:", e)
            time.sleep(2)

if __name__ == "__main__":
    network_worker({server_address})
"""
    script_path.write_text(script_content)

def cleanup_test_script(script_path):
    """Remove the test script."""
    try:
        script_path.unlink(missing_ok=True)
    except FileNotFoundError:
        pass

def terminate_process_using_file(file_path):
    """Terminate any process using the given file."""
    print(f"[DEBUG] Attempting to terminate processes using {file_path}...")
    for proc in psutil.process_iter(attrs=["open_files"]):
        try:
            open_files = proc.info.get("open_files", [])
            if open_files is None:
                continue
            if any(str(file_path) in str(f.path) for f in open_files):
                print(f"[DEBUG] Terminating process {proc.pid}")
                proc.terminate()
                proc.wait(timeout=5)
        except psutil.TimeoutExpired:
            print(f"[WARNING] Process {proc.pid} did not terminate in time.")
        except psutil.AccessDenied:
            print(f"[ERROR] Access denied for process {proc.pid}.")
        except psutil.NoSuchProcess:
            print(f"[ERROR] Process {proc.pid} does not exist.")
        except Exception as e:
            print(f"[ERROR] Could not terminate process {proc.pid}: {e}")

def fuzz_test_launcher(scripts_dir, server_address=("127.0.0.1", 65432), duration=30):
    """Run a fuzz test on the ScriptLauncherApp with network interactions."""
    initial_pids = get_python_pids()
    print(f"[TEST] Initial Python processes: {initial_pids}")

    stop_event = threading.Event()
    start_network_server(server_address[0], server_address[1], stop_event)

    test_script_path = scripts_dir / "test_script.py"
    create_test_script(test_script_path, server_address)
    print(f"[TEST] Test script created: {test_script_path}")

    root = tk.Tk()
    app = ScriptLauncherApp(root)

    def process_queue():
        """Process cleanup queue after fuzz testing."""
        print("[TEST] Cleaning up resources...")
        for tab_id in range(1, app.tab_manager.current_tab_id + 1):
            print(f"[TEST] Closing remaining tab {tab_id}...")
            app.tab_manager.close_tab(tab_id)
        terminate_process_using_file(test_script_path)
        cleanup_test_script(test_script_path)
        print("[TEST] Test script cleaned up.")

        # Use the app's shutdown mechanism with a callback
        def after_shutdown():
            print("[TEST] Shutdown complete.")
            # Final PID check
            final_pids = get_python_pids()
            print(f"[TEST] Final Python processes: {final_pids}")

            remaining_pids = final_pids - initial_pids
            if remaining_pids:
                print(f"[WARNING] The following Python processes were not terminated: {remaining_pids}")
            else:
                print("[TEST] All Python processes terminated successfully.")

        app.on_close(callback=after_shutdown)

    def start_fuzz_test():
        print("[TEST] Starting fuzz testing...")
        start_time = time.time()
        while time.time() - start_time < duration:
            app.load_script(test_script_path)
            time.sleep(random.uniform(0.5, 1.5))
        print("[TEST] Fuzz testing completed.")
        root.after(100, process_queue)  # Ensure process_queue is called after mainloop completes

    threading.Thread(target=start_fuzz_test, daemon=True).start()
    root.mainloop()

if __name__ == "__main__":
    scripts_dir = Path(__file__).resolve().parent / "Scripts"
    fuzz_test_launcher(scripts_dir, duration=30)
