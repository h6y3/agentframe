import os
import sys
from typing import Optional
from sqlalchemy import Engine
from sqlmodel import SQLModel, Session, select

from agentframe.secrets.models import SecretNode


class EncryptedVault:
    """Manages secrets with Fernet encryption.

    Encryption key is read from AGENTFRAME_SECRET_KEY env var.
    If missing on first run, a key is generated and written to .agentframe_key
    with a prominent warning.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self._fernet = self._load_fernet()
        SQLModel.metadata.create_all(self.engine)

    def _load_fernet(self):
        try:
            from cryptography.fernet import Fernet
        except ImportError:
            return None  # cryptography not installed; vault runs in plaintext-warn mode

        key = os.environ.get("AGENTFRAME_SECRET_KEY")
        if not key:
            key_file = ".agentframe_key"
            if os.path.exists(key_file):
                with open(key_file) as f:
                    key = f.read().strip()
            else:
                key = Fernet.generate_key().decode()
                with open(key_file, "w") as f:
                    f.write(key)
                print(
                    "\n[AgentFrame] WARNING: Generated new encryption key → .agentframe_key\n"
                    "  Set AGENTFRAME_SECRET_KEY env var to this value before deploying.\n"
                    "  Add .agentframe_key to .gitignore — never commit it.\n",
                    file=sys.stderr,
                )
        return Fernet(key.encode() if isinstance(key, str) else key)

    def declare(
        self,
        id: str,
        env_var: str,
        description: str = "",
        required_by: list | None = None,
    ) -> SecretNode:
        """Idempotent — safe to call on every startup to register a secret slot."""
        with Session(self.engine) as session:
            existing = session.get(SecretNode, id)
            if existing:
                return existing
            node = SecretNode(
                id=id,
                env_var=env_var,
                description=description,
                required_by=required_by or [],
            )
            session.add(node)
            session.commit()
            session.refresh(node)
            return node

    def set_value(self, id: str, plaintext: str) -> None:
        """Encrypt plaintext and store it."""
        encrypted = self._encrypt(plaintext)
        with Session(self.engine) as session:
            node = session.get(SecretNode, id)
            if node is None:
                raise KeyError(f"Secret '{id}' not declared. Call declare() first.")
            node.encrypted_value = encrypted
            session.add(node)
            session.commit()

    def get_value(self, id: str) -> Optional[str]:
        """Decrypt and return the value; None if not set."""
        with Session(self.engine) as session:
            node = session.get(SecretNode, id)
            if node is None or node.encrypted_value is None:
                return None
            return self._decrypt(node.encrypted_value)

    def get_env_dict(self) -> dict[str, str]:
        """Return {ENV_VAR: decrypted_value} for all secrets that have a value.

        Used by the deploy command to inject secrets into cloud environment variables.
        """
        result: dict[str, str] = {}
        with Session(self.engine) as session:
            nodes = list(session.exec(select(SecretNode)).all())
        for node in nodes:
            if node.encrypted_value is not None:
                value = self._decrypt(node.encrypted_value)
                if value is not None:
                    result[node.env_var] = value
        return result

    def list_all(self) -> list[SecretNode]:
        with Session(self.engine) as session:
            return list(session.exec(select(SecretNode)).all())

    def delete(self, id: str) -> None:
        with Session(self.engine) as session:
            node = session.get(SecretNode, id)
            if node:
                session.delete(node)
                session.commit()

    def _encrypt(self, plaintext: str) -> str:
        if self._fernet is None:
            return plaintext  # no-op if cryptography unavailable
        return self._fernet.encrypt(plaintext.encode()).decode()

    def _decrypt(self, ciphertext: str) -> Optional[str]:
        if self._fernet is None:
            return ciphertext
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except Exception:
            return None
