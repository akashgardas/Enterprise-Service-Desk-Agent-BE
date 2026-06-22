import pyotp

def generate_mfa_secret() -> str:
    """Generates a base32 TOTP secret."""
    return pyotp.random_base32()

def get_totp_uri(secret: str, email: str, issuer_name: str = "EnterpriseServiceDesk") -> str:
    """Generates the provisioning URI for TOTP apps (Google Authenticator)."""
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer_name)

def verify_totp_code(secret: str, code: str) -> bool:
    """Verifies a TOTP code against the secret. Includes a small drift window."""
    totp = pyotp.TOTP(secret)
    # Allows a tolerance of 1 step (30 seconds) backward/forward for network delay
    return totp.verify(code, valid_window=1)
