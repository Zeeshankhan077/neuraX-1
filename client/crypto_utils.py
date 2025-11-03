"""
NeuraX Client: Cryptographic Utilities Module

Purpose:
    Provides RSA and AES encryption/decryption for secure communication
    between client and compute node over WebRTC DataChannel.

Security Model:
    - RSA 2048-bit key pairs for secure AES key exchange
    - AES-256-GCM for symmetric encryption of actual payloads
    - Base64 encoding for binary-safe transmission over text channels
    - Each session generates fresh keys to prevent replay attacks
"""

import logging
import base64
import os
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

# Configure logging for crypto operations
logger = logging.getLogger(__name__)


class CryptoSession:
    """
    Manages cryptographic operations for a single NeuraX session.
    
    Each session:
    1. Generates a new RSA key pair
    2. Exchanges AES key using RSA encryption
    3. Uses AES-GCM for subsequent payload encryption
    """
    
    def __init__(self):
        """Initialize a new crypto session with fresh keys."""
        # Step 1: Generate RSA key pair for this session
        # RSA 2048-bit provides strong security while remaining performant
        self.private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        # Step 2: Extract public key for exchange
        self.public_key = self.private_key.public_key()
        
        # Step 3: AES key will be generated and shared after key exchange
        self.aes_key = None
        
        logger.info("Crypto session initialized with fresh RSA key pair")
    
    def get_public_key_pem(self):
        """
        Serialize public key to PEM format for transmission.
        
        Returns:
            str: PEM-formatted public key (Base64 encoded DER)
        
        Why PEM?
        - Standard format, human-readable boundaries
        - Easy to transmit as text over WebRTC
        - Base64 encoded for binary-safe text transmission
        """
        # Step 1: Serialize public key to DER (binary format)
        public_pem = self.public_key.serialize(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        # Step 2: Return as string for transmission
        return public_pem.decode('utf-8')
    
    def decrypt_rsa(self, encrypted_data: bytes) -> bytes:
        """
        Decrypt RSA-encrypted data using session private key.
        
        Args:
            encrypted_data: RSA-encrypted bytes
            
        Returns:
            bytes: Decrypted plaintext data
            
        Used for:
        - Decrypting the shared AES key from compute node
        """
        try:
            # Step 1: Decrypt using OAEP padding (PKCS#1 v1.5 alternative, more secure)
            # OAEP provides semantic security against chosen plaintext attacks
            plaintext = self.private_key.decrypt(
                encrypted_data,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            
            logger.debug("RSA decryption successful")
            return plaintext
            
        except Exception as e:
            logger.error(f"RSA decryption failed: {e}")
            raise
    
    def exchange_aes_key(self, encrypted_aes_key: str):
        """
        Receive and decrypt the shared AES key from compute node.
        
        Args:
            encrypted_aes_key: Base64-encoded RSA-encrypted AES key
            
        Side effects:
            Sets self.aes_key for subsequent AES operations
        """
        # Step 1: Decode from Base64 (web-safe text format)
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_aes_key.encode('utf-8'))
        
        # Step 2: Decrypt using RSA private key
        aes_key_bytes = self.decrypt_rsa(encrypted_bytes)
        
        # Step 3: Store for future AES operations
        self.aes_key = aes_key_bytes
        
        logger.info("AES key exchanged and stored (32 bytes for AES-256)")
    
    def generate_and_encrypt_aes_key(self, remote_public_key_pem: str) -> str:
        """
        Generate a fresh AES key and encrypt it with compute node's RSA public key.
        
        Args:
            remote_public_key_pem: Compute node's public key in PEM format
            
        Returns:
            str: Base64-encoded RSA-encrypted AES key
            
        Why this flow?
        - Client generates AES key (prevents MITM if only one key exchange)
        - Encrypt with compute node's public key (only compute can decrypt)
        - Hybrid encryption: RSA for key exchange, AES for bulk data
        """
        # Step 1: Generate random 32-byte key for AES-256
        aes_key_bytes = os.urandom(32)
        
        # Step 2: Store for encryption operations
        self.aes_key = aes_key_bytes
        
        # Step 3: Load compute node's public key
        remote_pub_key = serialization.load_pem_public_key(
            remote_public_key_pem.encode('utf-8'),
            backend=default_backend()
        )
        
        # Step 4: Encrypt AES key with RSA public key
        encrypted_aes = remote_pub_key.encrypt(
            aes_key_bytes,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        # Step 5: Base64 encode for text transmission
        encrypted_aes_b64 = base64.urlsafe_b64encode(encrypted_aes).decode('utf-8')
        
        logger.info("AES key generated and RSA-encrypted for transmission")
        return encrypted_aes_b64
    
    def encrypt_payload(self, plaintext: str) -> str:
        """
        Encrypt a payload using AES-256-GCM.
        
        Args:
            plaintext: String data to encrypt
            
        Returns:
            str: Base64-encoded encrypted data with authentication tag
            
        Why AES-GCM?
        - Authenticated encryption (integrity + confidentiality)
        - Parallelizable, fast hardware acceleration
        - Single nonce per session key (reuse not allowed, but forgery detected)
        """
        if not self.aes_key:
            raise ValueError("AES key not initialized. Perform key exchange first.")
        
        # Step 1: Convert plaintext to bytes
        plaintext_bytes = plaintext.encode('utf-8')
        
        # Step 2: Generate random 96-bit nonce (required for GCM)
        # Each encryption uses a fresh nonce to prevent pattern analysis
        nonce = os.urandom(12)
        
        # Step 3: Encrypt with AES-GCM
        # GCM automatically appends authentication tag for integrity verification
        aesgcm = AESGCM(self.aes_key)
        ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, None)
        
        # Step 4: Prepend nonce to ciphertext (needed for decryption)
        # Format: [nonce (12 bytes)][ciphertext+tag (variable)]
        full_ciphertext = nonce + ciphertext
        
        # Step 5: Base64 encode for binary-safe text transmission
        encrypted_b64 = base64.urlsafe_b64encode(full_ciphertext).decode('utf-8')
        
        logger.debug(f"Payload encrypted: {len(plaintext_bytes)} bytes -> {len(full_ciphertext)} bytes")
        return encrypted_b64
    
    def decrypt_payload(self, encrypted_b64: str) -> str:
        """
        Decrypt an AES-GCM encrypted payload.
        
        Args:
            encrypted_b64: Base64-encoded encrypted data with nonce
            
        Returns:
            str: Decrypted plaintext
            
        Security:
        - Throws InvalidTag if data was tampered with (authentication failure)
        - GCM mode ensures both confidentiality and integrity
        """
        if not self.aes_key:
            raise ValueError("AES key not initialized. Perform key exchange first.")
        
        try:
            # Step 1: Decode from Base64
            full_ciphertext = base64.urlsafe_b64decode(encrypted_b64.encode('utf-8'))
            
            # Step 2: Extract nonce (first 12 bytes) and ciphertext
            nonce = full_ciphertext[:12]
            ciphertext = full_ciphertext[12:]
            
            # Step 3: Decrypt with AES-GCM
            # This will raise InvalidTag if ciphertext was modified
            aesgcm = AESGCM(self.aes_key)
            plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, None)
            
            # Step 4: Convert back to string
            plaintext = plaintext_bytes.decode('utf-8')
            
            logger.debug(f"Payload decrypted successfully")
            return plaintext
            
        except InvalidTag:
            logger.error("Authentication failed: ciphertext was tampered with")
            raise ValueError("Decryption failed: data integrity check failed")
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            raise


# Notes:
# - This module is shared between client and compute node for symmetric operations
# - RSA key exchange ensures only intended recipient can decrypt AES key
# - AES-GCM provides authenticated encryption for all payloads
# - Base64 encoding enables binary data over text-based WebRTC channels
# - Each session generates fresh keys (perfect forward secrecy on session level)

