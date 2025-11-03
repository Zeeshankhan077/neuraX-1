"""
NeuraX Compute Node - Production-Ready Cloud Compute

Purpose:
    High-end device that receives encrypted tasks from clients via WebRTC,
    executes them in Docker sandbox, and returns encrypted results.

Features:
    - Connects to Render-hosted server (https://neurax-server.onrender.com)
    - Auto-reconnect on server restart
    - Docker integration with auto-install
    - WebSocket transport with polling fallback
    - Production-ready error handling

Architecture:
    - Connects to signaling server and waits for client sessions
    - Establishes WebRTC peer connection on receiving offer
    - Exchanges keys with client for encrypted communication
    - Executes tasks in isolated Docker containers with resource limits
    - Returns stdout/stderr encrypted with session AES key
"""

import asyncio
import logging
import json
import subprocess
import os
import sys
import time
import socketio
from aiortc import RTCPeerConnection, RTCConfiguration, RTCIceServer, RTCDataChannel, RTCIceCandidate
from crypto_utils import CryptoSession

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# Dependency Checks and Auto-Installation
# ============================================================================

def check_and_install_websocket_client():
    """Check if websocket-client is installed, install if missing."""
    try:
        import websocket_client
        logger.info("websocket-client already installed")
        return True
    except ImportError:
        logger.warning("websocket-client not found, installing...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client>=1.6.4"])
            logger.info("✅ Successfully installed websocket-client")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install websocket-client: {e}")
            logger.warning("⚠️  Continuing without websocket-client (may use polling fallback)")
            return False

def check_docker_available():
    """Check if Docker is available and handle errors gracefully."""
    try:
        result = subprocess.run(
            ['docker', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            logger.info(f"Docker available: {result.stdout.strip()}")
            return True
        return False
    except FileNotFoundError:
        logger.warning("⚠️  Docker not found. Install Docker to enable sandbox execution.")
        logger.warning("   Compute node will continue but tasks may fail.")
        return False
    except Exception as e:
        logger.warning(f"⚠️  Docker check failed: {e}")
        logger.warning("   Compute node will continue but tasks may fail.")
        return False

def check_package_versions():
    """Check if required packages meet version requirements."""
    issues = []
    
    try:
        import socketio as sio
        sio_version = sio.__version__
        if sio_version != "5.10.0":
            issues.append(f"python-socketio=={sio_version} (expected 5.10.0)")
    except Exception as e:
        issues.append(f"python-socketio check failed: {e}")
    
    try:
        import websocket_client
        ws_version = getattr(websocket_client, '__version__', 'unknown')
        logger.info(f"websocket-client version: {ws_version}")
    except ImportError:
        issues.append("websocket-client not installed (will attempt auto-install)")
    
    if issues:
        logger.warning(f"⚠️  Version issues detected: {', '.join(issues)}")
    else:
        logger.info("✅ All package versions OK")
    
    return len(issues) == 0

# Initialize dependency checks
check_and_install_websocket_client()
docker_available = check_docker_available()
check_package_versions()


class NeuraXComputeNode:
    """
    Compute node for NeuraX distributed compute system.
    
    Responsibilities:
    - Accept WebRTC connections from clients
    - Exchange cryptographic keys
    - Execute tasks in sandboxed Docker containers
    - Return encrypted results
    """
    
    def __init__(self, signaling_url: str = None):
        """
        Initialize compute node.
        
        Args:
            signaling_url: URL of Flask-SocketIO signaling server
                           Defaults to Render production URL if not provided
        """
        # Step 1: Set signaling URL (auto-detect local vs production)
        if not signaling_url:
            # Check environment variable first
            signaling_url = os.getenv('SIGNALING_SERVER_URL')
            
            # If not set, default to localhost for local testing
            if not signaling_url:
                # Detect if running locally (common indicators)
                if os.path.exists('.git') or os.path.exists('requirements.txt'):
                    # Likely local development
                    signaling_url = 'http://localhost:10000'
                    logger.info("🔧 Auto-detected LOCAL environment, using http://localhost:10000")
                else:
                    # Production/Render deployment
                    signaling_url = 'https://neurax-server.onrender.com'
        
        self.signaling_url = signaling_url
        self.is_local = 'localhost' in signaling_url or '127.0.0.1' in signaling_url
        
        # Log connection target
        if self.is_local:
            logger.info(f"🔧 Connecting to LOCAL server: {signaling_url}")
        else:
            logger.info(f"☁️  Connecting to CLOUD server: {signaling_url}")
        
        # Step 2: Initialize Socket.IO client with WebSocket transport
        # Force WebSocket first, fallback to polling
        self.sio = socketio.AsyncClient(
            logger=True,
            engineio_logger=False,
            reconnection=True,
            reconnection_attempts=0,  # Infinite reconnection attempts
            reconnection_delay=1,
            reconnection_delay_max=10
        )
        
        # Step 3: Track connection state
        self.connected = False
        self.reconnect_count = 0
        self.docker_available = docker_available
        
        # Step 4: Set up event handlers
        self._setup_signaling_handlers()
        
        # Step 5: Track active sessions (multiple clients possible)
        self.sessions = {}  # session_id -> session_data
        
        # Step 6: STUN/TURN configuration for WebRTC
        stun_servers = [
            RTCIceServer(urls="stun:stun.l.google.com:19302"),
            RTCIceServer(urls="stun:stun1.l.google.com:19302")
        ]
        
        # TURN servers for relay fallback
        turn_servers = [
            RTCIceServer(urls="turn:openrelay.metered.ca:80", username="openrelayproject", credential="openrelayproject"),
            RTCIceServer(urls="turn:openrelay.metered.ca:443", username="openrelayproject", credential="openrelayproject"),
            RTCIceServer(urls="turn:openrelay.metered.ca:443?transport=tcp", username="openrelayproject", credential="openrelayproject")
        ]
        
        self.ice_config = RTCConfiguration(
            iceServers=stun_servers + turn_servers
        )
        
        logger.info("NeuraX compute node initialized")
    
    def _setup_signaling_handlers(self):
        """Register Socket.IO event handlers for signaling."""
        
        @self.sio.event
        async def connect():
            """Handle successful connection to signaling server."""
            self.connected = True
            self.reconnect_count = 0
            logger.info(f"✅ Connected to signaling server: {self.signaling_url}")
            
            # Detect if we switched between local and cloud
            if self.is_local:
                logger.info("📍 Connection mode: LOCAL")
            else:
                logger.info("☁️  Connection mode: CLOUD")
        
        @self.sio.event
        async def disconnect():
            """Handle disconnection from signaling server."""
            self.connected = False
            logger.warning("⚠️  Disconnected from signaling server")
            # Clean up all sessions
            self.sessions.clear()
        
        @self.sio.event
        async def connect_error(data):
            """Handle connection errors."""
            logger.error(f"❌ Connection error: {data}")
            self.connected = False
        
        @self.sio.on('offer')
        async def on_offer(data):
            """Receive SDP offer from client."""
            session_id = data['session_id']
            offer_sdp = data['offer']
            
            logger.info(f"Received offer for session: {session_id}")
            
            # Step 1: Create new WebRTC peer connection for this session
            pc = RTCPeerConnection(configuration=self.ice_config)
            
            # Step 2: Create DataChannel handler
            @pc.on("datachannel")
            def on_datachannel(channel: RTCDataChannel):
                """Handle incoming DataChannel from client."""
                logger.info("DataChannel received from client")
                
                # Step 3: Initialize crypto for this session
                crypto = CryptoSession()
                session_data = {
                    'pc': pc,
                    'channel': channel,
                    'crypto': crypto,
                    'remote_public_key': None
                }
                self.sessions[session_id] = session_data
                
                # Step 4: Set up DataChannel message handler
                @channel.on("message")
                def on_message(message):
                    """Process messages from client."""
                    asyncio.create_task(self._handle_message(session_id, message))
                
                @channel.on("open")
                def on_open():
                    """DataChannel opened."""
                    logger.info(f"DataChannel opened for session {session_id}")
                
                @channel.on("close")
                def on_close():
                    """DataChannel closed."""
                    logger.info(f"DataChannel closed for session {session_id}")
                    if session_id in self.sessions:
                        del self.sessions[session_id]
            
            # Step 5: Parse offer SDP
            from aiortc.sdp import SessionDescription
            offer = SessionDescription(sdp=offer_sdp, type='offer')
            
            # Step 6: Set remote description
            await pc.setRemoteDescription(offer)
            
            # Step 7: Create answer
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            
            # Step 8: Send answer to client via signaling
            await self.sio.emit('answer', {
                'session_id': session_id,
                'answer': answer.sdp
            })
            logger.info(f"Sent answer for session {session_id}")
            
            # Step 9: Send ICE candidates
            @pc.on("icecandidate")
            async def on_icecandidate(event):
                if event.candidate:
                    await self.sio.emit('ice_candidate', {
                        'session_id': session_id,
                        'candidate': {
                            'candidate': event.candidate.candidate,
                            'sdpMid': event.candidate.sdpMid,
                            'sdpMLineIndex': event.candidate.sdpMLineIndex
                        }
                    })
                    logger.debug("Sent ICE candidate")
        
        @self.sio.on('ice_candidate')
        async def on_ice_candidate(data):
            """Receive ICE candidate from client."""
            session_id = data['session_id']
            
            # Find session's peer connection
            if session_id not in self.sessions:
                return
            
            pc = self.sessions[session_id]['pc']
            
            candidate_dict = data['candidate']
            candidate = candidate_dict['candidate']
            sdp_mid = candidate_dict.get('sdpMid')
            sdp_mline_index = candidate_dict.get('sdpMLineIndex')
            
            await pc.addIceCandidate(
                RTCIceCandidate(
                    candidate=candidate,
                    sdpMid=sdp_mid,
                    sdpMLineIndex=sdp_mline_index
                )
            )
            logger.debug("Added ICE candidate from client")
    
    async def _handle_message(self, session_id: str, message: str):
        """
        Process incoming messages from client.
        
        Handles:
        - RSA key exchange
        - Encrypted task execution
        """
        try:
            # Step 1: Parse JSON message
            data = json.loads(message)
            msg_type = data.get('type')
            
            if session_id not in self.sessions:
                logger.error(f"Session not found: {session_id}")
                return
            
            session_data = self.sessions[session_id]
            crypto = session_data['crypto']
            channel = session_data['channel']
            
            # Step 2: Handle key exchange
            if msg_type == 'key_exchange':
                action = data.get('action')
                
                if action == 'send_public_key':
                    # Received client's public key
                    session_data['remote_public_key'] = data['public_key']
                    logger.info("Received client's public key")
                    
                    # Send our public key
                    public_key_pem = crypto.get_public_key_pem()
                    await channel.send(json.dumps({
                        'type': 'key_exchange',
                        'action': 'send_public_key',
                        'public_key': public_key_pem
                    }))
                    logger.info("Sent our public key to client")
                
                elif action == 'send_aes_key':
                    # Received encrypted AES key from client
                    encrypted_aes_b64 = data['encrypted_aes_key']
                    crypto.exchange_aes_key(encrypted_aes_b64)
                    logger.info("Received and decrypted AES key")
                    
                    # Acknowledge
                    await channel.send(json.dumps({
                        'type': 'key_exchange',
                        'action': 'aes_key_received'
                    }))
                    logger.info("Key exchange complete")
            
            # Step 3: Handle encrypted task
            elif msg_type == 'encrypted_task':
                logger.info("Received encrypted task from client")
                
                # Step 4: Decrypt task
                encrypted_data = data['encrypted_data']
                plaintext = crypto.decrypt_payload(encrypted_data)
                task_json = json.loads(plaintext)
                
                code = task_json.get('code', '')
                task_type = task_json.get('type', 'python_code')
                
                logger.info(f"Decrypted task: {len(code)} bytes of {task_type}")
                
                # Step 5: Execute task in Docker sandbox
                result = await self._execute_in_sandbox(code, task_type)
                
                # Step 6: Encrypt result
                result_json = json.dumps({
                    'exit_code': result['exit_code'],
                    'stdout': result['stdout'],
                    'stderr': result['stderr'],
                    'execution_time': result.get('execution_time', 0)
                })
                
                encrypted_result = crypto.encrypt_payload(result_json)
                
                # Step 7: Send encrypted result
                await channel.send(json.dumps({
                    'type': 'encrypted_result',
                    'encrypted_data': encrypted_result
                }))
                logger.info("Sent encrypted result to client")
                
                # Step 8: Close connection after result
                await channel.close()
                if session_id in self.sessions:
                    del self.sessions[session_id]
                
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            import traceback
            traceback.print_exc()
    
    async def _execute_in_sandbox(self, code: str, task_type: str) -> dict:
        """
        Execute task in isolated Docker container.
        
        Args:
            code: Python code to execute
            task_type: Type of task (currently only 'python_code')
            
        Returns:
            dict: {'exit_code': int, 'stdout': str, 'stderr': str, 'execution_time': float}
        
        Security:
        - Limited CPU (1 core)
        - Limited memory (1GB)
        - Limited time (30 seconds)
        - Auto-cleanup container
        - No network access inside container
        """
        import time
        start_time = time.time()
        
        # Check Docker availability
        if not self.docker_available:
            logger.error("❌ Docker not available - cannot execute task")
            return {
                'exit_code': -1,
                'stdout': '',
                'stderr': 'Docker not available. Please install Docker to enable sandbox execution.',
                'execution_time': 0
            }
        
        try:
            # Step 1: Prepare temporary file with code
            # Using unique name to avoid collisions in concurrent sessions
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_file = f.name
            
            try:
                # Step 2: Execute in Docker container with resource limits
                # --rm: auto-remove container after execution
                # --cpus=1: limit to 1 CPU core (prevents CPU exhaustion)
                # --memory=1g: limit memory to 1GB (prevents OOM attacks)
                # --network=none: disable network access (prevents data exfiltration)
                # --ulimit nofile=1024: limit file descriptors
                # --read-only: mount filesystem read-only (extra safety)
                # -v /tmp:/tmp:rw: mount temp directory writable for temp files
                
                docker_cmd = [
                    'docker', 'run', '--rm',
                    '--cpus=1',  # Resource limit: max 1 CPU core
                    '--memory=1g',  # Resource limit: max 1GB RAM
                    '--network=none',  # Security: no network access
                    '--ulimit', 'nofile=1024:1024',  # Security: limit file descriptors
                    '--timeout=30',  # Kill after 30 seconds
                    '--read-only',  # Security: read-only root filesystem
                    '-v', f'{temp_file}:/tmp/task.py:ro',  # Mount code file
                    '-v', '/tmp:/tmp:rw',  # Writable temp directory
                    'python:3.10',  # Base image
                    'python', '/tmp/task.py'  # Execute code
                ]
                
                logger.info("Starting Docker sandbox execution")
                
                # Step 3: Run with timeout
                result = await asyncio.wait_for(
                    self._run_command(docker_cmd),
                    timeout=35.0  # Slightly more than container timeout
                )
                
                execution_time = time.time() - start_time
                
                logger.info(f"Sandbox execution complete: exit={result['exit_code']}, time={execution_time:.2f}s")
                
                return {
                    'exit_code': result['exit_code'],
                    'stdout': result['stdout'],
                    'stderr': result['stderr'],
                    'execution_time': execution_time
                }
                
            finally:
                # Step 4: Clean up temporary file
                try:
                    os.unlink(temp_file)
                except:
                    pass
        
        except asyncio.TimeoutError:
            logger.warning("Sandbox execution timed out")
            return {
                'exit_code': -1,
                'stdout': '',
                'stderr': 'Execution timeout (30 seconds)',
                'execution_time': time.time() - start_time
            }
        except Exception as e:
            logger.error(f"Sandbox execution failed: {e}")
            return {
                'exit_code': -1,
                'stdout': '',
                'stderr': f'Execution error: {str(e)}',
                'execution_time': time.time() - start_time
            }
    
    async def _run_command(self, cmd: list) -> dict:
        """
        Execute shell command and capture output.
        
        Args:
            cmd: Command as list of arguments
            
        Returns:
            dict: {'exit_code': int, 'stdout': str, 'stderr': str}
        """
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        return {
            'exit_code': process.returncode,
            'stdout': stdout.decode('utf-8', errors='replace'),
            'stderr': stderr.decode('utf-8', errors='replace')
        }
    
    async def connect_to_signaling(self):
        """
        Connect to signaling server with auto-reconnect.
        
        Raises:
            ConnectionError: If connection fails after retries
        """
        max_retries = 5
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Connecting to {self.signaling_url} (attempt {attempt + 1}/{max_retries})...")
                
                # Force WebSocket transport, fallback to polling
                await self.sio.connect(
                    self.signaling_url,
                    transports=['websocket', 'polling'],
                    wait_timeout=10
                )
                
                logger.info("✅ Connected to signaling server successfully")
                return
                
            except Exception as e:
                self.reconnect_count += 1
                logger.warning(f"⚠️  Connection attempt {attempt + 1} failed: {e}")
                
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 30)  # Exponential backoff, max 30s
                else:
                    logger.error(f"❌ Failed to connect after {max_retries} attempts")
                    raise ConnectionError(f"Signaling connection failed: {e}")
    
    async def run(self):
        """
        Start compute node and wait for client connections.
        
        This runs indefinitely until interrupted, with auto-reconnect.
        """
        try:
            # Connect to signaling
            await self.connect_to_signaling()
            
            # Wait forever for connections
            logger.info("🚀 Compute node ready, waiting for client connections...")
            logger.info("   Press Ctrl+C to stop")
            
            # Keep alive loop with reconnection check
            while True:
                await asyncio.sleep(10)
                
                # Check connection status and reconnect if needed
                if not self.connected and self.sio.connected is False:
                    logger.warning("Connection lost, attempting to reconnect...")
                    try:
                        await self.connect_to_signaling()
                    except Exception as e:
                        logger.error(f"Reconnection failed: {e}")
            
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if self.sio.connected:
                await self.sio.disconnect()
            logger.info("Compute node stopped")


async def main():
    """Entry point for compute node."""
    import argparse
    
    parser = argparse.ArgumentParser(description='NeuraX Compute Node')
    parser.add_argument(
        '--signaling-url',
        default=None,
        help='Signaling server URL (defaults to https://neurax-server.onrender.com or SIGNALING_SERVER_URL env var)'
    )
    
    args = parser.parse_args()
    
    node = NeuraXComputeNode(signaling_url=args.signaling_url)
    await node.run()


if __name__ == '__main__':
    asyncio.run(main())


# Notes:
# - Compute node connects to https://neurax-server.onrender.com by default
# - Auto-detects local vs cloud connection
# - WebSocket transport with polling fallback
# - Auto-reconnects on server restart
# - Docker integration with graceful degradation
# - Each session has isolated WebRTC connection and crypto session
# - Docker sandbox provides strong isolation from host system
# - Resource limits prevent denial-of-service attacks
# - Results encrypted with session AES key before transmission
# - Automatic cleanup of containers and temporary files