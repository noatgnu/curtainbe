from typing import Optional

from curtain.models import Curtain, DataAESEncryptionFactors


def apply_encryption_request(request_data, curtain: Curtain) -> Optional[DataAESEncryptionFactors]:
    """
    Validates a client's encryption request for a Curtain session and sets
    curtain.encrypted accordingly.

    curtain.encrypted is only ever set to True when the client also submitted
    a valid end-to-end encrypted AES key and IV, so a session can never end up
    flagged as encrypted while the file actually stored for it is plaintext.

    Returns the unsaved DataAESEncryptionFactors to persist once curtain has
    been saved and has a primary key, or None if no encryption factors apply.
    """
    if "encrypted" not in request_data:
        return None

    if request_data["encrypted"] != "True":
        curtain.encrypted = False
        return None

    if request_data.get("e2e") != "True" or "encryptedKey" not in request_data or "encryptedIV" not in request_data:
        curtain.encrypted = False
        return None

    curtain.encrypted = True
    return DataAESEncryptionFactors(
        encrypted_iv=request_data["encryptedIV"],
        encrypted_decryption_key=request_data["encryptedKey"],
    )
