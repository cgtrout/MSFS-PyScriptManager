import psutil
import threading
import random
import time
import socket
from pathlib import Path
from Launcher import ScriptLauncherApp, ScriptTab

def get_python_pids():
    """Get all active Python process PIDs."""
    return {p.pid for p in psutil.process_iter(attrs=["name"]) if p.info["name"] and "python" in p.info["name"].lower()}

def start_network_server(host="127.0.0.1", port=65432, stop_event=None):
    """Start a network server that randomly disconnects or delays clients."""
    def handle_client(conn, addr):
        print(f"[SERVER] Connected to {addr}")
        try:
            while not stop_event.is_set():
                # Simulate random disconnections
                if random.random() < 0.1:  # 10% chance to disconnect
                    print(f"[SERVER] Simulating disconnection for {addr}")
                    conn.close()
                    return

                # Simulate random delays
                if random.random() < 0.2:  # 20% chance of delay
                    delay = random.uniform(0.5, 2.0)  # Delay between 0.5 to 2 seconds
                    print(f"[SERVER] Simulating delay of {delay:.2f}s for {addr}")
                    time.sleep(delay)

                # Receive data
                data = conn.recv(1024)
                if not data:
                    print(f"[SERVER] Client {addr} disconnected")
                    return

                # Echo the data back
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
        except KeyboardInterrupt:
            print("[SERVER] Server shutting down.")
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
            time.sleep(2)  # Retry after a short delay

if __name__ == "__main__":
    network_worker({server_address})
    """
    script_path.write_text(script_content)


def cleanup_test_script(script_path):
    """Remove the test script."""
    try:
        script_path.unlink()  # Delete the file
    except FileNotFoundError:
        pass


def fuzz_test_launcher(scripts_dir, server_address=("127.0.0.1", 65432), duration=30):
    """Run a fuzz test on the ScriptLauncherApp with network interactions."""
    # Step 1: Capture Python processes before
    initial_pids = get_python_pids()
    print(f"[TEST] Initial Python processes: {initial_pids}")

    # Step 2: Start the network server
    stop_event = threading.Event()
    start_network_server(server_address[0], server_address[1], stop_event)

    # Step 3: Create the test script
    test_script = scripts_dir / "test_script.py"
    create_test_script(test_script, server_address)
    print(f"[TEST] Test script created: {test_script}")

    # Step 4: Start the ScriptLauncherApp in a separate thread
    root = None
    app = None

    def start_app():
        nonlocal root, app
        from tkinter import Tk
        root = Tk()
        app = ScriptLauncherApp(root)
        root.mainloop()

    app_thread = threading.Thread(target=start_app, daemon=True)
    app_thread.start()

    # Allow time for the app to initialize
    while not app:
        time.sleep(1)

    print("[TEST] App started. Opening Performance Monitor...")
    
    # Step 5: Open the Performance Monitor tab
    perf_tab_id = None
    try:
        perf_tab_id = app.tab_manager.generate_tab_id()  # Generate a unique ID for the PerfTab
        app.open_performance_metrics_tab()  # Open the performance monitoring tab
    except Exception as e:
        print(f"[TEST] Error opening Performance Monitor: {e}")

    print("[TEST] Performance Monitor tab opened. Beginning fuzz testing...")

    # Step 6: Randomized addition and closure of script tabs
    start_time = time.time()
    open_tabs = []
    tab_counter = 0

    try:
        while time.time() - start_time < duration:
            action = random.choice(["add", "close"])

            if action == "add" or not open_tabs:
                # Add a new script tab
                print("[TEST] Adding a new script tab...")
                app.load_script(test_script)
                tab_id = app.tab_manager.current_tab_id  # Get the most recently added tab ID
                open_tabs.append(tab_id)
                print(f"[TEST] Added tab {tab_id}.")
            elif action == "close" and open_tabs:
                # Close a random tab
                tab_id = random.choice(open_tabs)
                print(f"[TEST] Closing tab {tab_id}...")
                app.tab_manager.close_tab(tab_id)
                open_tabs.remove(tab_id)

            # Wait for a random interval between actions
            time.sleep(random.uniform(0.5, 2))

        print("[TEST] Fuzz testing completed.")

    except KeyboardInterrupt:
        print("[TEST] Fuzz testing interrupted by user.")

    finally:
        # Step 7: Cleanup
        print("[TEST] Cleaning up...")
        for tab_id in open_tabs:
            print(f"[TEST] Closing remaining tab {tab_id}...")
            app.tab_manager.close_tab(tab_id)

        if perf_tab_id is not None:
            print("[TEST] Closing Performance Monitor tab...")
            app.tab_manager.close_tab(perf_tab_id)

        cleanup_test_script(test_script)
        print("[TEST] Test script cleaned up.")
        root.quit()
        app_thread.join()
        stop_event.set()
        print("[TEST] Launcher app and server stopped.")

        # Step 8: Capture Python processes after
        final_pids = get_python_pids()
        print(f"[TEST] Final Python processes: {final_pids}")

        # Step 9: Ensure all new PIDs are terminated
        remaining_pids = final_pids - initial_pids
        if remaining_pids:
            print(f"[WARNING] The following Python processes were not terminated: {remaining_pids}")
        else:
            print("[TEST] All Python processes started by the app were terminated successfully.")

if __name__ == "__main__":
    scripts_dir = Path(__file__).resolve().parent / "Scripts"  # Directory for the test script
    fuzz_test_launcher(scripts_dir, duration=30)  # Run the test for 30 seconds
