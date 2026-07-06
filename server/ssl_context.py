"""
SSL/TLS context management for BNC server.
"""

import ssl
import os
from typing import Optional, Tuple


def create_ssl_context(cert_file: str, key_file: str) -> Optional[ssl.SSLContext]:
    """Create SSL context for server."""
    if not os.path.exists(cert_file):
        print(f"[SSL] Certificate not found: {cert_file}")
        return None
    
    if not os.path.exists(key_file):
        print(f"[SSL] Key not found: {key_file}")
        return None
    
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(cert_file, key_file)
        
        # Strong cipher suites
        context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')
        
        return context
    except Exception as e:
        print(f"[SSL] Failed to create context: {e}")
        return None


def generate_self_signed_cert(hostname: str, cert_path: str, key_path: str) -> bool:
    """Generate self-signed certificate for testing."""
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime
        
        # Generate key
        key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        
        # Generate certificate
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "IRC BNC"),
            x509.NameAttribute(NameOID.COMMON_NAME, hostname),
        ])
        
        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.datetime.utcnow()
        ).not_valid_after(
            datetime.datetime.utcnow() + datetime.timedelta(days=365)
        ).add_extension(
            x509.SubjectAlternativeName([x509.DNSName(hostname)]),
            critical=False
        ).sign(key, hashes.SHA256())
        
        # Write to files
        with open(key_path, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))
        
        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        
        return True
        
    except ImportError:
        print("[SSL] cryptography module required for cert generation")
        return False
    except Exception as e:
        print(f"[SSL] Failed to generate cert: {e}")
        return False