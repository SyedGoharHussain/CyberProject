"""
Attacker Node - Post-Quantum Blockchain Attack Simulator
=========================================================
Runs independently in its own terminal.
Listens for network traffic and simulates attack scenarios.
"""

import socket
import time
import threading
import sys
import json
import random

ATTACKER_BANNER = """
╔══════════════════════════════════════════════════════════════╗
║            ATTACKER NODE - INDEPENDENT PROCESS               ║
║            Listening for transaction traffic...               ║
║            Ready to inject tampered data                      ║
╚══════════════════════════════════════════════════════════════╝
"""

def separator(title: str = ""):
    line = "═" * 62
    if title:
        pad = (62 - len(title) - 2) // 2
        print(f"\n{'═'*pad} {title} {'═'*pad}")
    else:
        print(f"\n{line}")


def run_attacker_listener(host='127.0.0.1', port=9999, duration=120, tamper_probability=0.5):
    """
    Run attacker node in listen mode.
    Accepts connections and simulates attack scenarios.
    
    Args:
        host: IP to bind to
        port: Port to listen on
        duration: How long to keep listening (seconds)
        tamper_probability: Probability of tampering each transaction (0.0 to 1.0)
    """
    print(ATTACKER_BANNER)
    separator("ATTACKER INITIALIZATION")
    
    print(f"\n[Attacker] Binding to {host}:{port}")
    print(f"[Attacker] Listen timeout: {duration} seconds")
    print(f"[Attacker] Tampering probability: {int(tamper_probability*100)}%")
    print(f"[Attacker] Waiting for defender to connect and send transactions...")
    
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, port))
        server.listen(5)
        server.settimeout(1)  # Non-blocking with timeout
        
        print(f"\n[Attacker] ✓ Socket bound successfully")
        print(f"[Attacker] ✓ Listening for incoming transactions...")
        
        separator("ATTACK MONITORING - INTERCEPTING TRAFFIC")
        
        start_time = time.time()
        connection_count = 0
        attack_attempts = 0
        tamper_success = 0
        
        while time.time() - start_time < duration:
            try:
                client_socket, address = server.accept()
                connection_count += 1
                
                print(f"\n[Attacker] ✗✗✗ Connection #{connection_count} from {address}")
                
                # Receive transaction data
                try:
                    data = client_socket.recv(4096)
                    if data:
                        print(f"[Attacker] → Intercepted {len(data)} bytes of transaction data")
                        
                        # Decide whether to tamper based on probability
                        should_tamper = random.random() < tamper_probability
                        
                        if should_tamper:
                            # Tamper with the data
                            tampered_data = bytearray(data)
                            # Flip bits in signature portion (usually in middle)
                            if len(tampered_data) > 100:
                                tamper_idx = len(tampered_data) // 2
                                tampered_data[tamper_idx] ^= 0xFF
                                tampered_data[tamper_idx + 1] ^= 0xFF
                            
                            print(f"[Attacker] → CORRUPTING signature bytes...")
                            print(f"[Attacker] → Sending TAMPERED transaction back to defender")
                            client_socket.send(bytes(tampered_data))
                            attack_attempts += 1
                            tamper_success += 1
                        else:
                            # Let it pass through
                            print(f"[Attacker] → Letting transaction pass (random decision)")
                            client_socket.send(data)
                            attack_attempts += 1
                            
                except Exception as e:
                    print(f"[Attacker] → Error during tampering: {e}")
                
                client_socket.close()
                
            except socket.timeout:
                elapsed = time.time() - start_time
                remaining = duration - elapsed
                continue
            except Exception as e:
                print(f"[Attacker] Error: {e}")
        
        separator("ATTACK SUMMARY")
        print(f"\n[Attacker] Total connections intercepted: {connection_count}")
        print(f"[Attacker] Transaction interceptions attempted: {attack_attempts}")
        print(f"[Attacker] Successful corruptions: {tamper_success}")
        print(f"[Attacker] Transactions passed through: {attack_attempts - tamper_success}")
        print(f"[Attacker] Listener completed. Shutting down...")
        
    except Exception as e:
        print(f"\n[Attacker Error] Failed to start: {e}")
        sys.exit(1)
    finally:
        try:
            server.close()
            print("[Attacker] ✓ Socket closed")
        except:
            pass


if __name__ == "__main__":
    print("\n" + "="*62)
    print("ATTACKER CONFIGURATION")
    print("="*62)
    
    mode = input("\n[Config] Choose mode:\n  1) AUTOMATIC (120s listen, 50% tampering rate)\n  2) MANUAL (custom settings)\n\nEnter choice (1 or 2): ").strip()
    
    if mode == "2":
        print("\n[Config] MANUAL MODE - Configure Attack Strategy")
        try:
            duration = int(input("[Config] Listen duration in seconds (default 120): ").strip() or "120")
            port = int(input("[Config] Port number to listen on (default 9999): ").strip() or "9999")
            tamper_rate = input("[Config] Tampering strategy:\n  1) Tamper ALL incoming transactions (100%)\n  2) Tamper HALF of transactions (50%)\n  3) Tamper RANDOM % (enter custom %)\n\nEnter choice (1, 2, or 3): ").strip()
            
            if tamper_rate == "1":
                tampering_desc = "100% (ALL transactions)"
                tamper_prob = 1.0
            elif tamper_rate == "2":
                tampering_desc = "50% (HALF of transactions)"
                tamper_prob = 0.5
            elif tamper_rate == "3":
                try:
                    custom_pct = int(input("[Config] Enter tampering percentage (0-100): ").strip() or "50")
                    custom_pct = max(0, min(100, custom_pct))
                    tampering_desc = f"{custom_pct}% of transactions"
                    tamper_prob = custom_pct / 100.0
                except ValueError:
                    tampering_desc = "50% (invalid input, using default)"
                    tamper_prob = 0.5
            else:
                tampering_desc = "50% (invalid input, using default)"
                tamper_prob = 0.5
                
        except ValueError:
            print("[Config] Invalid input, using defaults")
            duration = 120
            port = 9999
            tampering_desc = "50%"
            tamper_prob = 0.5
    else:
        print("\n[Config] AUTOMATIC MODE")
        duration = 120
        port = 9999
        tampering_desc = "50%"
        tamper_prob = 0.5
    
    print(f"\n[Config] Attacker Strategy:")
    print(f"  - Listen duration: {duration} seconds")
    print(f"  - Port: {port}")
    print(f"  - Tampering rate: {tampering_desc}")
    print("="*62 + "\n")
    
    run_attacker_listener(host='127.0.0.1', port=port, duration=duration, tamper_probability=tamper_prob)
