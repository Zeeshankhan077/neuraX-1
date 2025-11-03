"""
NeuraX Client

Purpose:
    Low-end device that connects to signaling server, establishes WebRTC connection
    with compute node, and submits encrypted tasks for remote execution.

Workflow:
    1. Connect to signaling server via Socket.IO
    2. Create WebRTC peer connection with STUN/TURN configuration
    3. Exchange RSA public keys with compute node
    4. Encrypt task with AES-256 and send over DataChannel
    5. Receive encrypted result and decrypt
"""

import asyncio
import logging
import json
import socketio
from aiortc import RTCPeerConnection, RTCConfiguration, RTCIceServer, RTCDataChannel, RTCIceCandidate
from aiortc.contrib.media import MediaRelay
from crypto_utils import CryptoSession

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class NeuraXClient:
    """
    Client for NeuraX distributed compute system.
    
    Manages:
    - Signaling server connection
    - WebRTC peer-to-peer setup
    - Cryptographic operations
    - Task submission and result retrieval
    """
    
    def __init__(self, signaling_url: str, session_id: str = None):
        """
        Initialize NeuraX client.
        
        Args:
            signaling_url: URL of Flask-SocketIO server
            session_id: Optional session ID (generates random if None)
        """
        self.signaling_url = signaling_url
        
        # Step 1: Generate unique session ID if not provided
        if not session_id:
            import uuid
            session_id = str(uuid.uuid4())
        self.session_id = session_id
        
        # Step 2: Initialize Socket.IO client for signaling
        self.sio = socketio.AsyncClient()
        self._setup_signaling_handlers()
        
        # Step 3: Initialize WebRTC peer connection
        # STUN servers help discover public IP for NAT traversal
        # TURN servers relay traffic if direct connection fails
        stun_servers = [
            RTCIceServer(urls="stun:stun.l.google.com:19302"),
            RTCIceServer(urls="stun:stun1.l.google.com:19302")
        ]
        
        # TURN server for relay fallback (using free public STUN/TURN servers)
        turn_servers = [
            RTCIceServer(urls="turn:openrelay.metered.ca:80", username="openrelayproject", credential="openrelayproject"),
            RTCIceServer(urls="turn:openrelay.metered.ca:443", username="openrelayproject", credential="openrelayproject"),
            RTCIceServer(urls="turn:openrelay.metered.ca:443?transport=tcp", username="openrelayproject", credential="openrelayproject")
        ]
        
        self.pc = RTCPeerConnection(
            configuration=RTCConfiguration(
                iceServers=stun_servers + turn_servers
            )
        )
        
        # Step 4: Initialize cryptographic session
        self.crypto = CryptoSession()
        
        # Step 5: Track connection state
        self.channel = None
        self.connected = False
        self.remote_public_key = None
        
        logger.info(f"NeuraX client initialized with session: {self.session_id}")
    
    def _setup_signaling_handlers(self):
        """Register Socket.IO event handlers for signaling."""
        
        @self.sio.event
        async def connect():
            """Handle successful connection to signaling server."""
            logger.info("Connected to signaling server")
            
            # Step 1: Create session on server
            await self.sio.emit('create_session', {
                'session_id': self.session_id
            })
            logger.info(f"Requested session creation: {self.session_id}")
        
        @self.sio.event
        async def disconnect():
            """Handle disconnection from signaling server."""
            logger.info("Disconnected from signaling server")
            self.connected = False
        
        @self.sio.on('session_created')
        async def on_session_created(data):
            """Session successfully created, ready for compute node."""
            logger.info(f"Session created: {data}")
        
        @self.sio.on('answer')
        async def on_answer(data):
            """Receive SDP answer from compute node."""
            logger.info("Received SDP answer from compute node")
            
            # Step 1: Parse answer SDP
            from aiortc.sdp import SessionDescription
            answer = SessionDescription(sdp=data['answer'], type='answer')
            
            # Step 2: Set remote description (compute node's answer)
            await self.pc.setRemoteDescription(answer)
            
            logger.info("Set remote description from compute node")
        
        @self.sio.on('ice_candidate')
        async def on_ice_candidate(data):
            """Receive ICE candidate from compute node."""
            if data.get('from') == self.sio.sid:
                return  # Ignore own candidates
            
            # Step 1: Parse ICE candidate
            candidate_dict = data['candidate']
            candidate = candidate_dict['candidate']
            sdp_mid = candidate_dict.get('sdpMid')
            sdp_mline_index = candidate_dict.get('sdpMLineIndex')
            
            # Step 2: Add candidate to peer connection
            await self.pc.addIceCandidate(
                RTCIceCandidate(
                    candidate=candidate,
                    sdpMid=sdp_mid,
                    sdpMLineIndex=sdp_mline_index
                )
            )
            logger.debug("Added ICE candidate from compute node")
    
    async def connect_to_signaling(self):
        """
        Connect to signaling server via Socket.IO.
        
        Raises:
            ConnectionError: If connection fails
        """
        try:
            await self.sio.connect(self.signaling_url)
            logger.info("Connected to signaling server successfully")
        except Exception as e:
            logger.error(f"Failed to connect to signaling server: {e}")
            raise ConnectionError(f"Signaling connection failed: {e}")
    
    def setup_data_channel(self):
        """
        Create WebRTC DataChannel for encrypted communication.
        
        DataChannel provides:
        - Reliable, ordered message delivery
        - Low latency for small payloads
        - End-to-end encryption (layered with our crypto)
        """
        # Step 1: Create DataChannel with ordered delivery
        self.channel = self.pc.createDataChannel('neurax-channel')
        
        # Step 2: Set up DataChannel event handlers
        @self.channel.on("open")
        def on_channel_open():
            """DataChannel opened, ready for communication."""
            logger.info("DataChannel opened with compute node")
            self.connected = True
            
            # Step 3: Send our public key to compute node
            asyncio.create_task(self._initiate_key_exchange())
        
        @self.channel.on("message")
        def on_channel_message(message):
            """Receive message from compute node."""
            logger.info("Received message from compute node")
            asyncio.create_task(self._handle_message(message))
        
        @self.channel.on("close")
        def on_channel_close():
            """DataChannel closed."""
            logger.info("DataChannel closed")
            self.connected = False
    
    async def _initiate_key_exchange(self):
        """
        Initiate RSA key exchange with compute node.
        
        Flow:
        1. Send our public key (PEM format)
        2. Receive compute node's public key
        3. Generate AES key and encrypt with compute's RSA key
        4. Send encrypted AES key
        """
        try:
            # Step 1: Send our public key
            public_key_pem = self.crypto.get_public_key_pem()
            await self.channel.send(json.dumps({
                'type': 'key_exchange',
                'action': 'send_public_key',
                'public_key': public_key_pem
            }))
            logger.info("Sent public key to compute node")
            
            # Wait for response handled in _handle_message
        except Exception as e:
            logger.error(f"Key exchange failed: {e}")
    
    async def _handle_message(self, message):
        """
        Process incoming messages from compute node.
        
        Handles:
        - RSA key exchange (public key receipt)
        - Encrypted task results
        """
        try:
            # Step 1: Parse JSON message
            data = json.loads(message)
            msg_type = data.get('type')
            
            # Step 2: Handle key exchange
            if msg_type == 'key_exchange':
                action = data.get('action')
                if action == 'send_public_key':
                    # Received compute node's public key
                    self.remote_public_key = data['public_key']
                    logger.info("Received compute node's public key")
                    
                    # Generate AES key and send encrypted
                    encrypted_aes = self.crypto.generate_and_encrypt_aes_key(
                        self.remote_public_key
                    )
                    
                    await self.channel.send(json.dumps({
                        'type': 'key_exchange',
                        'action': 'send_aes_key',
                        'encrypted_aes_key': encrypted_aes
                    }))
                    logger.info("Sent encrypted AES key to compute node")
                
                elif action == 'aes_key_received':
                    # Key exchange complete
                    logger.info("Key exchange complete, ready for tasks")
                    
            # Step 3: Handle encrypted result
            elif msg_type == 'encrypted_result':
                logger.info("Received encrypted result from compute node")
                
                # Decrypt result
                encrypted_result = data['encrypted_data']
                result = self.crypto.decrypt_payload(encrypted_result)
                
                # Parse result JSON
                result_data = json.loads(result)
                
                # Display result
                print("\n" + "="*60)
                print("COMPUTE NODE RESULT:")
                print("="*60)
                print(f"Exit Code: {result_data.get('exit_code')}")
                print(f"\nSTDOUT:\n{result_data.get('stdout', '')}")
                if result_data.get('stderr'):
                    print(f"\nSTDERR:\n{result_data.get('stderr', '')}")
                print("="*60 + "\n")
                
                # Disconnect
                await self.disconnect()
                
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def create_offer(self):
        """
        Create WebRTC offer and send to compute node via signaling.
        
        This initiates the peer-to-peer connection establishment.
        """
        # Step 1: Create DataChannel before offer
        self.setup_data_channel()
        
        # Step 2: Create SDP offer
        offer = await self.pc.createOffer()
        
        # Step 3: Set local description
        await self.pc.setLocalDescription(offer)
        
        # Step 4: Send offer to signaling server (relayed to compute)
        await self.sio.emit('offer', {
            'session_id': self.session_id,
            'offer': offer.sdp
        })
        logger.info("Sent SDP offer to compute node")
        
        # Step 5: Send ICE candidates as they're discovered
        @self.pc.on("icecandidate")
        async def on_icecandidate(event):
            """Emit ICE candidates for NAT traversal."""
            if event.candidate:
                await self.sio.emit('ice_candidate', {
                    'session_id': self.session_id,
                    'candidate': {
                        'candidate': event.candidate.candidate,
                        'sdpMid': event.candidate.sdpMid,
                        'sdpMLineIndex': event.candidate.sdpMLineIndex
                    }
                })
                logger.debug("Sent ICE candidate")
    
    async def submit_task(self, task_payload: str):
        """
        Submit an encrypted task to compute node for execution.
        
        Args:
            task_payload: Python code or command to execute (string)
        
        Waits for:
        - WebRTC connection establishment
        - Key exchange completion
        - Result receipt
        """
        # Step 1: Wait for DataChannel to be ready
        timeout = 30  # seconds
        start_time = asyncio.get_event_loop().time()
        
        while not self.connected or not self.crypto.aes_key:
            if asyncio.get_event_loop().time() - start_time > timeout:
                raise TimeoutError("Connection timeout: compute node not ready")
            await asyncio.sleep(0.1)
        
        # Step 2: Create task JSON
        task_json = json.dumps({
            'code': task_payload,
            'type': 'python_code'
        })
        
        # Step 3: Encrypt task with AES-GCM
        encrypted_task = self.crypto.encrypt_payload(task_json)
        
        # Step 4: Send encrypted task over DataChannel
        await self.channel.send(json.dumps({
            'type': 'encrypted_task',
            'encrypted_data': encrypted_task
        }))
        logger.info("Sent encrypted task to compute node")
    
    async def disconnect(self):
        """
        Cleanly disconnect from signaling server and close WebRTC.
        
        Releases all connections and resources.
        """
        logger.info("Disconnecting...")
        
        if self.channel:
            self.channel.close()
        
        await self.pc.close()
        
        if self.sio.connected:
            await self.sio.disconnect()
        
        logger.info("Disconnected")


async def main():
    """
    Example usage of NeuraX client.
    
    This demonstrates submitting a Python task for remote execution.
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='NeuraX Client')
    parser.add_argument('--signaling-url', default='http://localhost:5000',
                        help='Signaling server URL')
    parser.add_argument('--session-id', default=None,
                        help='Session ID (auto-generated if not provided)')
    parser.add_argument('--task', default=None,
                        help='Python code to execute (or use default example)')
    
    args = parser.parse_args()
    
    # Default example task
    if not args.task:
        args.task = """
# Example task: calculate fibonacci
def fib(n):
    if n <= 1:
        return n
    return fib(n-1) + fib(n-2)

result = fib(30)
print(f"Fibonacci(30) = {result}")
"""
    
    # Step 1: Initialize client
    client = NeuraXClient(
        signaling_url=args.signaling_url,
        session_id=args.session_id
    )
    
    try:
        # Step 2: Connect to signaling server
        await client.connect_to_signaling()
        
        # Step 3: Create offer and establish WebRTC connection
        await client.create_offer()
        
        # Step 4: Wait a bit for connection to stabilize
        await asyncio.sleep(2)
        
        # Step 5: Submit task
        await client.submit_task(args.task)
        
        # Step 6: Wait for result (disconnect happens in message handler)
        await asyncio.sleep(60)  # Max wait time
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        await client.disconnect()


if __name__ == '__main__':
    asyncio.run(main())


# Notes:
# - Client uses python-socketio for signaling server communication
# - aiortc provides WebRTC peer connection and DataChannel
# - Cryptographic operations delegated to crypto_utils module
# - Async/await pattern for non-blocking I/O
# - Automatic ICE candidate exchange for NAT traversal
# - Graceful disconnection and resource cleanup
